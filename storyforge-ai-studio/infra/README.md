# Infrastructure

Infrastructure deployment is intentionally not automated in the starter pack. No command here creates billable AWS resources.

- `aws/` will contain the reviewed production AWS deployment plan/CDK or Terraform after account, region, credits and budget are confirmed.
- `policies/` contains lifecycle/security policy examples only; review bucket names, retention and permissions before applying.
- Never use root credentials. Use IAM roles/short-lived credentials and least privilege.
