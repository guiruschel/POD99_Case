## Data Engineering Checklist

For every pipeline, consider:

### Reliability
- idempotency
- retries
- failure recovery
- partial failures

### Data Quality
- nullability
- uniqueness
- referential integrity
- schema changes
- duplicate records

### Performance
- partitioning
- predicate pushdown
- unnecessary scans
- memory usage
- parallelism

### Observability
- structured logging
- metrics
- error tracking
- pipeline duration

### Security
- secrets
- IAM permissions
- PII
- encryption

### Testing
- unit tests
- integration tests
- data quality tests