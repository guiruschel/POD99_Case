# Terraform owns the catalog database (infrastructure). The bronze/silver/gold
# Iceberg tables themselves are created by the Spark jobs via CREATE TABLE,
# since table DDL is tightly coupled to the job's schema logic, not infra.
resource "aws_glue_catalog_database" "this" {
  name        = replace("${var.project_name}_${var.environment}", "-", "_")
  description = "Catalog database for the Financas balance pipeline (bronze/silver/gold Iceberg tables)"
}
