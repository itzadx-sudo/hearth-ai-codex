```python
from shared_model import load_model
model = load_model()
status_logits, risk_logits, attention = model(x)
```

Input: a float32 tensor `x` of shape `[N, 8]`, including `N=1`.
Wrong dtype or shape raises `ValueError`; inputs are never silently cast.
The model loads on CPU in eval mode with all parameters frozen.
Outputs: status logits `[N, 3]`, risk logits `[N, 1]`, attention `[N, 8]`.
Attention rows sum to approximately 1 (tolerance `1e-4`).
Repeated calls on the same input produce identical outputs.
This folder must not be edited. Distribute all four files unchanged.
