from pathlib import Path as _Path
import hashlib as _hashlib
import pickle as _pickle
from types import SimpleNamespace as _SimpleNamespace

import torch as _torch

from ._tabnet import TabNet as _TabNet, _InferenceModel

__all__ = ["load_model"]


class _UnusedDtype:
    def __init__(self, *args):
        pass

    def __setstate__(self, state):
        pass


def _discard_scalar(*args):
    return None


class _CheckpointUnpickler(_pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) == ("numpy", "dtype"):
            return _UnusedDtype
        if (module, name) == ("numpy._core.multiarray", "scalar"):
            return _discard_scalar
        return super().find_class(module, name)


def load_model():
    """Load the packaged network on CPU for float32 [N, 8] inference."""
    checkpoint_path, = _Path(__file__).parent.glob("*.pth")
    try:
        checkpoint = _torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except _pickle.UnpicklingError as exc:
        if "Unsupported global: GLOBAL numpy._core.multiarray.scalar" not in str(exc):
            raise
        trusted_sha256 = "9960f898d775cc7b984e530238f09ce0487a62684ba574475c8094fda1d18728"
        if _hashlib.sha256(checkpoint_path.read_bytes()).hexdigest() != trusted_sha256:
            raise ValueError("Checkpoint does not match the original trusted SHA-256.") from exc
        # The original trusted checkpoint contains an unused NumPy scalar metric.
        # weights_only=False is needed; discard only its dtype/scalar metadata
        # through a stdlib unpickler so loading needs no NumPy dependency.
        pickle_module = _SimpleNamespace(
            Unpickler=_CheckpointUnpickler, load=_pickle.load, __name__="pickle"
        )
        checkpoint = _torch.load(
            checkpoint_path, map_location="cpu", weights_only=False,
            pickle_module=pickle_module,
        )
    network = _TabNet(
        input_dim=checkpoint.get("input_dim", 8),
        output_dim=checkpoint.get("output_dim", 3),
        n_d=checkpoint.get("n_d", 32),
        n_a=checkpoint.get("n_a", 32),
        n_steps=checkpoint.get("n_steps", 5),
    )
    network.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model = _InferenceModel(network)
    model.requires_grad_(False)
    model.eval()
    return model
