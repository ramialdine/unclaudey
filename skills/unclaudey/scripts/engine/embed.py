"""Text-image embedding model wrapper (open_clip). Imported only by setup and search."""
from __future__ import annotations

import time
import warnings

import numpy as np

from . import config
from .util import log

PHOTO_PREFIXES = ("a photo", "photo of", "an image", "a picture", "a close-up", "a closeup", "an aerial", "a black and white")


def as_prompt(text: str) -> str:
    t = " ".join(text.strip().split())
    return t if t.lower().startswith(PHOTO_PREFIXES) else f"a photo of {t}"


class Embedder:
    def __init__(self, model_key: str | None = None, device: str | None = None):
        t0 = time.time()
        import torch
        import open_clip

        self.torch = torch
        self.key = model_key or config.DEFAULT_MODEL
        name, pretrained = config.MODELS[self.key]
        if device is None:
            if torch.backends.mps.is_available():
                device = "mps"
            elif torch.cuda.is_available():
                device = "cuda"
            else:
                device = "cpu"
        self.device = device
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=pretrained)
        model.eval()
        # half precision on GPUs: ~3x faster, embeddings match fp32 to cos > 0.999
        self.dtype = torch.float16 if device in ("mps", "cuda") else torch.float32
        self.model = model.to(device=device, dtype=self.dtype)
        self.preprocess = preprocess
        ls = getattr(model, "logit_scale", None)
        self.logit_scale = float(ls.detach().float().exp()) if ls is not None else 100.0
        self.tokenizer = open_clip.get_tokenizer(name)
        log(f"model {name} ({pretrained}) on {device} loaded in {time.time() - t0:.1f}s")

    def text(self, texts: list[str]) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            tok = self.tokenizer(texts).to(self.device)
            f = self.model.encode_text(tok)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def prompts(self, texts: list[str]) -> np.ndarray:
        return self.text([as_prompt(t) for t in texts])

    def tensors(self, pil_images) -> list:
        return [self.preprocess(im.convert("RGB")) for im in pil_images]

    def images(self, pil_images=None, tensors=None) -> np.ndarray:
        torch = self.torch
        if tensors is None:
            tensors = self.tensors(pil_images)
        batch = torch.stack(tensors).to(device=self.device, dtype=self.dtype)
        with torch.no_grad():
            f = self.model.encode_image(batch)
            f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()


# Zero-shot "is there a person in this photo": softmax over person vs. other-subject prompts,
# scaled by the model's own logit scale. AUC ~0.89 against keyword labels on the Lite index.
PEOPLE_POS = ["a photo of a person", "a photo of people", "a photo of a man", "a photo of a woman",
              "a photo of a child", "a photo of a crowd"]
PEOPLE_NEG = ["a photo of an animal", "a photo of a landscape", "a photo of a plant", "a photo of food",
              "a photo of a building", "a photo of an object", "a photo of a city street", "a photo of the sky",
              "a photo of an interior", "a photo of a vehicle", "a photo of the ocean", "a photo of a flower"]


def people_probability(emb: "Embedder", feats: np.ndarray) -> np.ndarray:
    P, N = emb.prompts(PEOPLE_POS), emb.prompts(PEOPLE_NEG)
    logits = np.concatenate([feats @ P.T, feats @ N.T], axis=1) * emb.logit_scale
    logits -= logits.max(axis=1, keepdims=True)
    pr = np.exp(logits)
    pr /= pr.sum(axis=1, keepdims=True)
    return pr[:, : len(P)].sum(axis=1)
