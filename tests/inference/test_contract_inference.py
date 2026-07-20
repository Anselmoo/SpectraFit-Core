from oracles.bench_contract import CI, CaseInference, InferenceConfig


def test_case_inference_round_trips_camelcase():
    ci = CaseInference(
        case_id="EZ-001",
        speedup_ci=CI(lo=8.0, point=10.0, hi=12.0),
        delta_r2_ci=CI(lo=-1e-4, point=0.0, hi=1e-4),
    )
    wire = ci.model_dump(by_alias=True)
    assert wire["caseId"] == "EZ-001"
    assert wire["speedupCi"]["point"] == 10.0
    assert CaseInference.model_validate(wire).case_id == "EZ-001"


def test_inference_config_is_preregistered():
    cfg = InferenceConfig(
        equivalence_margin=1e-3, bootstrap_b=2000, seed=20260612, fdr_q=0.05
    )
    assert cfg.bootstrap_b == 2000
