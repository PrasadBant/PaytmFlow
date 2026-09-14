from app.docai.confidence import ConfidenceInputs, compose_confidence


def test_high_signal_all_validated_yields_high_confidence():
    conf = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.95,
            classification_confidence=0.9,
            field_found=True,
            field_validated=True,
        )
    )
    assert conf > 0.7


def test_field_not_found_yields_low_confidence():
    conf_found = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.9,
            classification_confidence=0.9,
            field_found=True,
            field_validated=True,
        )
    )
    conf_not_found = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.9,
            classification_confidence=0.9,
            field_found=False,
            field_validated=False,
        )
    )
    assert conf_not_found < conf_found


def test_poor_ocr_pulls_confidence_down_even_if_field_found():
    conf = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.2,
            classification_confidence=0.95,
            field_found=True,
            field_validated=True,
        )
    )
    assert conf < 0.3


def test_deterministic_repeated_calls_give_identical_result():
    # Manifest-confidence-calibration phase (Part 12 "calibration
    # correctness"): `compose_confidence` is pure arithmetic over its
    # inputs - no randomness, no hidden state, no I/O - so it must be
    # byte-identical across repeated calls with the same inputs.
    inputs = ConfidenceInputs(
        ocr_confidence=0.87, classification_confidence=0.91, field_found=True, field_validated=True
    )
    results = {compose_confidence(inputs) for _ in range(20)}
    assert len(results) == 1


def test_monotonic_in_ocr_confidence():
    # Higher OCR confidence must never DECREASE composed confidence, all
    # else equal - a basic sanity property any future calibration must
    # preserve, and a real regression target if it's ever broken.
    values = [
        compose_confidence(
            ConfidenceInputs(
                ocr_confidence=oc,
                classification_confidence=0.9,
                field_found=True,
                field_validated=True,
            )
        )
        for oc in (0.3, 0.5, 0.7, 0.9, 1.0)
    ]
    assert values == sorted(values)


def test_monotonic_in_classification_confidence():
    values = [
        compose_confidence(
            ConfidenceInputs(
                ocr_confidence=0.9,
                classification_confidence=cc,
                field_found=True,
                field_validated=True,
            )
        )
        for cc in (0.3, 0.5, 0.7, 0.9, 1.0)
    ]
    assert values == sorted(values)


def test_bad_evidence_never_scores_higher_than_good_evidence():
    # Confidence must not increase for known-bad evidence without
    # justification (Part 12's "calibration behavior" requirement) - a
    # document with poor OCR AND a field that failed validation must
    # never outscore a clean, fully-validated document.
    good = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.9,
            classification_confidence=0.9,
            field_found=True,
            field_validated=True,
        )
    )
    bad = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.4,
            classification_confidence=0.5,
            field_found=False,
            field_validated=False,
        )
    )
    assert bad < good


def test_realistic_correct_document_composes_below_typical_manifest_threshold():
    # Documents the ROOT CAUSE traced during the manifest-integrity +
    # confidence-calibration phase's audit, as a concrete, permanent
    # regression rather than only prose in a report: a genuinely correct,
    # fully-validated document with REALISTIC (not perfect) OCR and
    # classification confidence - both independently strong at ~0.87-0.90 -
    # still composes to well under the 0.80-0.85 manifest thresholds used
    # across all six journeys, purely because `base = ocr_confidence *
    # classification_confidence` multiplies two sub-1.0 numbers together.
    # This is not a bug in the formula (it's honest, unfabricated
    # arithmetic over two real signals) - it is the documented, measured
    # reason correct evidence often lands below threshold, matched
    # against real per-sample measurements in
    # docs/docai_manifest_confidence_report.md Part 5/6. If this test
    # ever starts failing because the formula changed, that's exactly the
    # kind of change future calibration work needs to notice and
    # re-evaluate deliberately, not accidentally.
    conf = compose_confidence(
        ConfidenceInputs(
            ocr_confidence=0.88,
            classification_confidence=0.89,
            field_found=True,
            field_validated=True,
        )
    )
    assert conf < 0.80


def test_output_always_bounded_0_to_1():
    for oc in (0.0, 0.5, 1.0):
        for cc in (0.0, 0.5, 1.0):
            for found in (True, False):
                for validated in (True, False):
                    conf = compose_confidence(
                        ConfidenceInputs(
                            ocr_confidence=oc,
                            classification_confidence=cc,
                            field_found=found,
                            field_validated=validated,
                        )
                    )
                    assert 0.0 <= conf <= 1.0
