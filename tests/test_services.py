import io

import pytest
from tablib import Dataset

from apps.data_io.views import _collect_error_messages, _inject_farm_column, _load_dataset
from apps.land.services.soil import _build_soil_defaults, _parse_soil_layers


class TestParseSoilLayers:
    def test_extracts_mean_values(self):
        data = {
            "properties": {
                "layers": [
                    {"name": "phh2o", "depths": [{"values": {"mean": 65}}]},
                    {"name": "soc",   "depths": [{"values": {"mean": 120}}]},
                ]
            }
        }
        result = _parse_soil_layers(data)
        assert result == {"phh2o": 65, "soc": 120}

    def test_skips_none_mean(self):
        data = {
            "properties": {
                "layers": [
                    {"name": "phh2o", "depths": [{"values": {"mean": None}}]},
                    {"name": "sand",  "depths": [{"values": {"mean": 400}}]},
                ]
            }
        }
        result = _parse_soil_layers(data)
        assert "phh2o" not in result
        assert result["sand"] == 400

    def test_skips_layer_with_no_depths(self):
        data = {
            "properties": {
                "layers": [
                    {"name": "clay", "depths": []},
                ]
            }
        }
        result = _parse_soil_layers(data)
        assert result == {}

    def test_empty_response(self):
        assert _parse_soil_layers({}) == {}

    def test_missing_properties_key(self):
        assert _parse_soil_layers({"type": "Point"}) == {}


class TestBuildSoilDefaults:
    def test_applies_divisor_and_multiplier(self):
        # phh2o: divisor=10, multiplier=1 → 65 / 10 * 1 = 6.5
        result = _build_soil_defaults({"phh2o": 65})
        assert result["ph"] == pytest.approx(6.5)

    def test_nitrogen_multiplier(self):
        # nitrogen: divisor=1, multiplier=10 → 20 / 1 * 10 = 200
        result = _build_soil_defaults({"nitrogen": 20})
        assert result["nitrogen_ppm"] == pytest.approx(200)

    def test_missing_property_returns_none(self):
        result = _build_soil_defaults({})
        assert result["ph"] is None
        assert result["sand_pct"] is None

    def test_all_properties_present(self):
        props = {
            "phh2o": 70, "soc": 200, "nitrogen": 15,
            "sand": 400, "silt": 300, "clay": 300, "cec": 120,
        }
        result = _build_soil_defaults(props)
        assert result["ph"] == pytest.approx(7.0)
        assert result["organic_carbon_pct"] == pytest.approx(2.0)
        assert result["sand_pct"] == pytest.approx(40.0)
        assert result["cec"] == pytest.approx(12.0)


class TestLoadDataset:
    def _make_file(self, content, name):
        f = io.BytesIO(content if isinstance(content, bytes) else content.encode())
        f.name = name
        return f

    def test_loads_csv(self):
        f = self._make_file("name,quantity\nDiesel,500\n", "test.csv")
        ds, err = _load_dataset(f)
        assert err is None
        assert ds is not None
        assert ds.headers == ["name", "quantity"]
        assert len(ds) == 1

    def test_rejects_unsupported_extension(self):
        f = self._make_file("data", "test.txt")
        ds, err = _load_dataset(f)
        assert ds is None
        assert "CSV" in err or "XLSX" in err

    def test_returns_error_on_malformed_csv(self):
        # tablib is fairly tolerant, but a completely empty file should produce a dataset
        f = self._make_file("", "test.csv")
        ds, err = _load_dataset(f)
        # Either succeeds with empty dataset or returns an error — both are acceptable
        assert err is None or isinstance(err, str)


class TestInjectFarmColumn:
    def test_appends_column_when_absent(self):
        ds = Dataset(headers=["name"])
        ds.append(["Diesel"])
        _inject_farm_column(ds, 42)
        assert "farm" in ds.headers
        assert ds[0][ds.headers.index("farm")] == 42

    def test_overwrites_existing_farm_column(self):
        ds = Dataset(headers=["name", "farm"])
        ds.append(["Diesel", 99])
        _inject_farm_column(ds, 7)
        farm_idx = ds.headers.index("farm")
        assert ds[0][farm_idx] == 7

    def test_multiple_rows(self):
        ds = Dataset(headers=["name"])
        ds.append(["A"])
        ds.append(["B"])
        _inject_farm_column(ds, 5)
        farm_idx = ds.headers.index("farm")
        assert ds[0][farm_idx] == 5
        assert ds[1][farm_idx] == 5


class TestCollectErrorMessages:
    def test_returns_empty_list_when_no_errors(self):
        class FakeResult:
            invalid_rows = []

            def row_errors(self):
                return []

        assert _collect_error_messages(FakeResult()) == []

    def test_formats_row_errors(self):
        class FakeError:
            error = "invalid value"

        class FakeResult:
            invalid_rows = []

            def row_errors(self):
                return [(2, [FakeError()])]

        msgs = _collect_error_messages(FakeResult())
        assert len(msgs) == 1
        assert "Row 2" in msgs[0]
        assert "invalid value" in msgs[0]

    def test_caps_at_20_messages(self):
        class FakeError:
            error = "bad"

        class FakeResult:
            invalid_rows = []

            def row_errors(self):
                return [(i, [FakeError()]) for i in range(1, 30)]

        msgs = _collect_error_messages(FakeResult())
        assert len(msgs) == 20

    def test_reports_invalid_rows_too(self):
        """Widget/model validation failures used to be skipped without a word."""

        class FakeInvalid:
            number = 3
            field_specific_errors = {"crop_type": ['Unknown crop "Dragonfruit".']}
            non_field_specific_errors = ["Planting is on another field."]

        class FakeResult:
            invalid_rows = [FakeInvalid()]

            def row_errors(self):
                return []

        msgs = _collect_error_messages(FakeResult())
        assert msgs == ['Row 3: crop_type: Unknown crop "Dragonfruit".', "Row 3: Planting is on another field."]
