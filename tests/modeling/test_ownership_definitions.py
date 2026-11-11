import pandas as pd
import pytest

from steam_data import OWNER_COLUMNS, OWNER_LB, OWNER_MID, OWNER_UB, add_estimated_owner_columns, ownership_target


def test_bounds_midpoints_and_ordered_targets():
    source = pd.DataFrame({"Estimated owners": ["0 - 20000", " 20000-50000 ", "50000 - 100000",
                                                "100000 - 200000", "0 - 0"]}, index=[8, 4, 9, 1, 3])
    result = add_estimated_owner_columns(source)
    assert result[OWNER_LB].tolist() == [0, 20000, 50000, 100000, 0]
    assert result[OWNER_UB].tolist() == [20000, 50000, 100000, 200000, 0]
    assert result[OWNER_MID].tolist() == [10000, 35000, 75000, 150000, 0]
    assert ownership_target(result).tolist() == [0, 1, 1, 2, 0]
    assert result.index.equals(source.index) and list(source) == ["Estimated owners"]


@pytest.mark.parametrize("value", [None, "invalid", "50000 - 20000", "-1 - 20000", "0 - inf"])
def test_invalid_intervals_can_be_audited_or_rejected(value):
    source = pd.DataFrame({"Estimated owners": [value, "0 - 20000"]})
    with pytest.raises(ValueError, match="Invalid"):
        add_estimated_owner_columns(source)
    result = add_estimated_owner_columns(source, strict=False)
    assert result.loc[0, OWNER_COLUMNS].isna().all()
    assert result.loc[1, OWNER_MID] == 10000


def test_derived_columns_are_recomputed_and_crossing_ranges_rejected():
    result = add_estimated_owner_columns(pd.DataFrame({"Estimated owners": ["10000 - 50000"],
        OWNER_LB: [-1], OWNER_UB: [-1], OWNER_MID: [-1]}))
    assert result.loc[0, OWNER_MID] == 30000
    with pytest.raises(ValueError, match="crosses"):
        ownership_target(result)


def test_ownership_fields_are_not_service_features():
    from steam_service.features import BASE_NUMERIC, ENGINEERED
    assert not set(OWNER_COLUMNS) & set(BASE_NUMERIC + ENGINEERED)
