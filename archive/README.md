# Archived model experiment

`ML_Model.ipynb` and `ML_Model_docs/` preserve the historical Random Forest experiment and its figures. They are not part of the live application, which serves constant-course dead reckoning only.

The evaluation is invalid: predictions were snapped to held-out test targets and AIS rows were split randomly. The reported scores cannot support accuracy claims. Do not use the notebook as an evaluation template or load its model into serving code.

The leakage post-mortem is tracked in [issue #20](https://github.com/imaddde867/NaviCast/issues/20). Link its reproducible report here when it exists. The optional notebook dependencies remain in `requirements-notebook.txt` at the repository root; this archive is preserved for inspection, not maintained as an executable pipeline.
