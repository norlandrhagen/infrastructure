import re

import pandas as pd
from google.cloud import bigquery
from prometheus_pandas import query

from ..grafana.grafana_utils import get_cluster_prometheus


class BigqueryCostImporter:
    """Bigquery Cost Importer for GCP clusters

    Args:
        cluster (dict): parsed cluster.yaml
    """

    def __init__(self, cluster: dict, query=None):
        self.cluster = cluster

        # TODO(pnasrat): Pass client in or encapsulate in an class?
        self.client = bigquery.Client()

        # TODO(pnasrat): we are using GCP project name not cluster name.
        self.cluster_project_name = cluster["gcp"]["project"]
        self.bq = cluster["gcp"]["billing"]["bigquery"]

        self.table_name = f'{self.bq["project"]}.{self.bq["dataset"]}.gcp_billing_export_resource_v1_{self.bq["billing_id"].replace("-", "_")}'
        # Make sure the table name only has alphanumeric characters, _ and -
        assert re.match(r"^[a-zA-Z0-9._-]+$", self.table_name)

        if query is None:
            self.query = f"""
            SELECT
            invoice.month as month,
            project.id as project,
            (SUM(CAST(cost AS NUMERIC))
                + SUM(IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC))
                            FROM UNNEST(credits) AS c), 0)))
                AS total_with_credits
            FROM `{self.table_name}`
            WHERE invoice.month >= @start_month
                AND invoice.month <= @end_month
                AND project.id = @project
            GROUP BY 1, 2
            ORDER BY invoice.month ASC
            ;
            """
        else:
            self.query = query

    def get_costs(self, start_month, end_month):
        df = self._run_query(start_month, end_month)
        df["month"] = pd.to_datetime(df["month"], format="%Y%m")
        return df

    def _run_query(self, start_month, end_month):
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "start_month", "STRING", start_month.strftime("%Y%m")
                ),
                bigquery.ScalarQueryParameter(
                    "end_month", "STRING", end_month.strftime("%Y%m")
                ),
                bigquery.ScalarQueryParameter(
                    "project", "STRING", self.cluster_project_name
                ),
            ]
        )
        result = self.client.query(self.query, job_config=job_config).result()
        return result.to_dataframe()


class PrometheusUtilizationImporter:
    """Prometheus Utilization Importer for shared GCP clusters

    Args:
        cluster (dict): parsed cluster.yaml
    """

    def __init__(self, cluster: dict):
        self.cluster = cluster

    def get_costs(self, start_month, end_month):
        rows = self._run_query(start_month, end_month)
        return self.clean_query(rows)

    def _run_query(self, start_month, end_month):
        # Write doc string
        url, s = get_cluster_prometheus(self.cluster.get("name"))
        p = query.Prometheus(url, http=s)
        prom_query = """sum(
        kube_pod_container_resource_requests{resource="memory",unit="byte"}
        ) by (namespace)
        """
        start = start_month.isoformat()
        end = end_month.isoformat()
        step = "24h"
        rows = p.query_range(prom_query, start, end, step)
        return rows

    def clean_query(self, rows):
        # This only handles single prometheus namespace labels rather than any general prometheus query.
        # The regex should be for an RFC 1123 DNS_LABEL however we're only querying namespaces so strict
        # validation not as necessary
        # https://github.com/kubernetes/design-proposals-archive/blob/main/architecture/identifiers.md
        rows.rename(
            columns=lambda c: re.sub(
                r".*=\"(?P<namespace>[a-zA-Z0-9-]+)\"}", r"\g<namespace>", c
            ),
            inplace=True,
        )

        rows.index.names = ["month"]
        rows.fillna(0, inplace=True)
        rows = rows.resample("MS", axis=0).sum()
        # Calculate utilization
        # rows = rows.div(rows.sum(axis=1), axis=0)
        # Combined support
        # rows["support_combined"] = rows["support"] + rows["kube-system"]
        return rows


def get_cluster_costs(cluster, start_month, end_month):
    tenancy = cluster.get("tenancy", "dedicated")
    if tenancy == "shared":
        return get_shared_hub_costs(cluster, start_month, end_month)
    elif tenancy == "dedicated":
        return get_dedicated_cluster_costs(cluster, start_month, end_month)
    return pd.DataFrame()
    # return get_dedicated_cluster_costs(cluster, start_month, end_month)


def get_dedicated_cluster_costs(cluster, start_month, end_month):
    """Return monthly costs for a dedicated cluster for a range of months

    Args:
        cluster (dict): parsed cluster.yaml
        start_month (datetime): Starting month
        end_month (datetime): End month

    Returns:
        rows (dataframe of costs per project)
    """
    bq_importer = BigqueryCostImporter(cluster)
    result = bq_importer.get_costs(start_month, end_month)
    return result


# TODO(pnasrat): wire in prometheus values
def get_shared_hub_costs(cluster, start_month, end_month):
    costs = get_dedicated_cluster_costs(cluster, start_month, end_month)
    prom_importer = PrometheusUtilizationImporter(cluster)
    utilization = prom_importer.get_costs(start_month, end_month)
    totals = costs.merge(utilization, how="left", on="month")
    totals.iloc[:, 2:].multiply(totals.iloc[:, 1].astype(float), axis=0)
    return totals


def get_support_hub_costs(cluster, start_month, end_month):
    return pd.DataFrame()


def uptime_checks_cost(
    client, start_month, end_month, cluster_project_name, table_name
):
    # TODO(pnasrat): parameterize
    query = """SELECT
        invoice.month as month,
        project.id as project,
        (SUM(CAST(cost AS NUMERIC))
            + SUM(IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC))
                        FROM UNNEST(credits) AS c), 0)))
            AS total_with_credits
        FROM `two-eye-two-see.cloud_costs.gcp_billing_export_resource_v1_0157F7_E3EA8C_25AC3C`
        WHERE invoice.month >= "202201"
              AND invoice.month <= "202304"
              AND project.id = "two-eye-two-see"
              AND service.id = "58CD-E7C3-72CA"
        GROUP BY 1, 2
        ORDER BY invoice.month ASC
        ;
    """
    CLOUD_MONITORING_SVC = "58CD-E7C3-72CA"
    return 0
