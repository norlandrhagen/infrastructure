import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pandera import Check, Column, DataFrameSchema, DateTime, Float, Index, String
from ruamel.yaml import YAML

from deployer.billing import cost_importer

yaml = YAML(typ="safe", pure=True)


@pytest.fixture
def cluster_yaml():
    test_cluster = """
    name: awi-ciroh
    provider: gcp
    gcp:
        project: awi-ciroh
        cluster: awi-ciroh-cluster
        zone: us-central1
        billing:
            paid_by_us: true
            bigquery:
                project: two-eye-two-see
                dataset: cloud_costs
                billing_id: 00DEAD-BEEF000-012345
    """

    c = yaml.load(test_cluster)
    return c


@pytest.fixture
def schema():
    schema = DataFrameSchema(
        {
            "month": Column(DateTime),
            "project": Column(String),
            "total_with_credits": Column(Float, Check(lambda x: x > 0.0), coerce=True),
        }
    )
    return schema


@pytest.fixture
def prom_schema():
    schema = DataFrameSchema(
        {
            "aup": Column(Float, Check(lambda x: x > 0.0), coerce=True),
        },
        index=Index(DateTime),
    )
    return schema


def test_cost_schema(cluster_yaml, schema):
    bq_importer = cost_importer.BigqueryCostImporter(cluster_yaml)
    bq_importer._run_query = MagicMock(
        return_value=pd.DataFrame(
            {
                "month": ["202301"],
                "project": ["test-cluster"],
                "total_with_credits": [42.0],
            }
        )
    )
    start_date = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    end_date = datetime.datetime(2023, 3, 1, tzinfo=datetime.timezone.utc)
    schema.validate(bq_importer.get_costs(start_date, end_date))


def test_shared_cluster_importer(cluster_yaml, prom_schema):
    cluster_yaml["tenancy"] = "shared"

    shared_importer = cost_importer.PrometheusUtilizationImporter(cluster_yaml)
    shared_importer._run_query = MagicMock(
        return_value=pd.DataFrame(
            {'{namespace="aup"}': [1.0] * 31},
            index=pd.date_range(start="2023-01-01", end="2023-01-31", freq="D"),
        )
    )

    start_date = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
    end_date = datetime.datetime(2023, 2, 1, tzinfo=datetime.timezone.utc)
    rows = shared_importer.get_costs(start_date, end_date)
    prom_schema.validate(rows)
    assert rows["aup"].item() == 31.0
