"""Built-in industry presets for SkillForge AI."""

from typing import Any, Dict, List

PRESETS: Dict[str, Dict[str, Any]] = {
    "aws-iam-least-privilege-auditor": {
        "id": "aws-iam-least-privilege-auditor",
        "name": "aws-iam-least-privilege-auditor",
        "title": "AWS IAM Least-Privilege & Trust Policy Auditor",
        "category": "Cloud Security (AWS IAM)",
        "version": "1.2.0",
        "description": (
            "Audits AWS IAM identity policies and Role Trust policies for wildcard '*' actions, "
            "privilege escalation vectors (iam:PassRole + ec2:RunInstances), cross-account trust "
            "without ExternalId/MFA conditions, and stale access keys (>90 days). Use when auditing "
            "AWS environments against CIS AWS Foundations Benchmark and NIST 800-53 AC-6."
        ),
        "frameworks": ["CIS AWS v3.0", "NIST 800-53 AC-6", "ISO 27001 A.8.2"],
        "input_type": "json_policy_bundle",
        "cli_flags": [
            "--input-file",
            "--max-key-age-days",
            "--strict-external-id",
            "--output-format",
        ],
        "guardrails": [
            "Read-only policy evaluation: never mutates live AWS IAM roles or detaches policies automatically.",
            "Flags any Principal: '*' in AssumeRolePolicyDocument as CRITICAL unless restricted by aws:PrincipalOrgID.",
            "Produces canonical sorted JSON output with deterministic SHA-256 verification digest.",
        ],
        "rules": [
            {
                "rule_id": "IAM-001",
                "title": "Wildcard Action with Wildcard Resource",
                "severity": "CRITICAL",
                "control": "NIST 800-53 AC-6(1)",
                "check": "wildcard_action_and_resource",
                "remediation": "Scope Action list to explicit service API verbs and bind Resource to specific ARNs.",
            },
            {
                "rule_id": "IAM-002",
                "title": "Privilege Escalation via iam:PassRole + Compute Launch",
                "severity": "HIGH",
                "control": "CIS AWS 1.16",
                "check": "passrole_escalation",
                "remediation": "Restrict iam:PassRole Resource to approved execution role ARNs and add iam:PassedToService condition.",
            },
            {
                "rule_id": "IAM-003",
                "title": "Cross-Account Trust Missing sts:ExternalId or aws:MultiFactorAuthPresent",
                "severity": "HIGH",
                "control": "SOC 2 CC6.1",
                "check": "unconstrained_trust_policy",
                "remediation": "Add Condition block requiring sts:ExternalId or aws:MultiFactorAuthPresent = true.",
            },
            {
                "rule_id": "IAM-004",
                "title": "IAM Access Key Rotation Exceeds 90-Day SLA",
                "severity": "MEDIUM",
                "control": "CIS AWS 1.14",
                "check": "stale_access_key",
                "remediation": "Rotate IAM user access keys every 90 days or migrate workload to short-lived OIDC IAM Roles.",
            },
        ],
        "sample_input": {
            "account_id": "123456789012",
            "environment": "production",
            "max_key_age_days": 90,
            "roles": [
                {
                    "role_name": "prod-ci-deployer-role",
                    "arn": "arn:aws:iam::123456789012:role/prod-ci-deployer-role",
                    "trust_principal": "arn:aws:iam::998877665544:root",
                    "require_external_id": False,
                    "require_mfa": False,
                    "statements": [
                        {
                            "sid": "AllowFullAdminFallback",
                            "effect": "Allow",
                            "actions": ["*"],
                            "resources": ["*"],
                        },
                        {
                            "sid": "PassRoleToWorkloads",
                            "effect": "Allow",
                            "actions": ["iam:PassRole", "ec2:RunInstances", "lambda:CreateFunction"],
                            "resources": ["*"],
                        },
                    ],
                    "access_key_age_days": 142,
                },
                {
                    "role_name": "prod-readonly-metrics-role",
                    "arn": "arn:aws:iam::123456789012:role/prod-readonly-metrics-role",
                    "trust_principal": "arn:aws:iam::123456789012:role/monitoring-collector",
                    "require_external_id": True,
                    "require_mfa": True,
                    "statements": [
                        {
                            "sid": "CloudWatchReadOnly",
                            "effect": "Allow",
                            "actions": ["cloudwatch:GetMetricData", "cloudwatch:ListMetrics"],
                            "resources": ["arn:aws:cloudwatch:us-east-1:123456789012:metric/*"],
                        }
                    ],
                    "access_key_age_days": 18,
                },
            ],
        },
    },
    "k8s-zero-trust-network-verifier": {
        "id": "k8s-zero-trust-network-verifier",
        "name": "k8s-zero-trust-network-verifier",
        "title": "Kubernetes Zero-Trust Network & Pod Security Verifier",
        "category": "DevSecOps (Kubernetes)",
        "version": "1.1.0",
        "description": (
            "Verifies Kubernetes Namespace NetworkPolicies, PodSecurityStandards (restricted profile), "
            "container securityContext privileges, and RBAC ClusterRoleBindings against NSA/CISA "
            "Kubernetes Hardening Guidelines. Use when validating K8s manifests before cluster admission."
        ),
        "frameworks": ["NSA/CISA K8s v1.2", "CIS Kubernetes v1.8", "NIST 800-190"],
        "input_type": "k8s_manifest_bundle",
        "cli_flags": [
            "--manifest-json",
            "--require-default-deny",
            "--disallow-cluster-admin",
            "--output-format",
        ],
        "guardrails": [
            "Performs offline static manifest verification without calling kubectl delete or mutating live etcd state.",
            "Requires both Ingress and Egress default-deny NetworkPolicy per production namespace.",
            "Enforces non-root execution (runAsNonRoot: true) and read-only root filesystems.",
        ],
        "rules": [
            {
                "rule_id": "K8S-001",
                "title": "Namespace Missing Default-Deny Ingress/Egress NetworkPolicy",
                "severity": "CRITICAL",
                "control": "NSA/CISA K8s 4.1",
                "check": "missing_default_deny_netpol",
                "remediation": "Deploy a default-deny NetworkPolicy with podSelector: {} and policyTypes: [Ingress, Egress].",
            },
            {
                "rule_id": "K8S-002",
                "title": "Privileged Container or allowPrivilegeEscalation Enabled",
                "severity": "CRITICAL",
                "control": "CIS K8s 5.2.1",
                "check": "privileged_container",
                "remediation": "Set securityContext.privileged: false and allowPrivilegeEscalation: false.",
            },
            {
                "rule_id": "K8S-003",
                "title": "ClusterRoleBinding Grants cluster-admin to Broad Group or Default SA",
                "severity": "HIGH",
                "control": "CIS K8s 5.1.1",
                "check": "cluster_admin_binding",
                "remediation": "Replace cluster-admin with namespace-scoped RoleBindings granting minimal verb/resource tuples.",
            },
            {
                "rule_id": "K8S-004",
                "title": "Container Missing Memory/CPU Limits or ReadOnlyRootFilesystem",
                "severity": "MEDIUM",
                "control": "NIST 800-190 4.3",
                "check": "missing_hardening_limits",
                "remediation": "Set securityContext.readOnlyRootFilesystem: true and configure resources.limits.cpu/memory.",
            },
        ],
        "sample_input": {
            "cluster_name": "eks-prod-us-west-2",
            "namespaces": [
                {
                    "name": "payments-api",
                    "has_default_deny_ingress": False,
                    "has_default_deny_egress": False,
                    "workloads": [
                        {
                            "name": "checkout-worker",
                            "kind": "Deployment",
                            "privileged": True,
                            "allow_privilege_escalation": True,
                            "run_as_non_root": False,
                            "read_only_root_fs": False,
                            "has_resource_limits": False,
                            "cluster_role": "cluster-admin",
                        }
                    ],
                },
                {
                    "name": "ledger-core",
                    "has_default_deny_ingress": True,
                    "has_default_deny_egress": True,
                    "workloads": [
                        {
                            "name": "ledger-writer",
                            "kind": "StatefulSet",
                            "privileged": False,
                            "allow_privilege_escalation": False,
                            "run_as_non_root": True,
                            "read_only_root_fs": True,
                            "has_resource_limits": True,
                            "cluster_role": "ledger-namespace-reader",
                        }
                    ],
                },
            ],
        },
    },
    "soc2-continuous-control-monitor": {
        "id": "soc2-continuous-control-monitor",
        "name": "soc2-continuous-control-monitor",
        "title": "AICPA SOC 2 Type II Continuous Control Monitor",
        "category": "GRC & Compliance (SOC 2 / ISO 27001)",
        "version": "1.3.0",
        "description": (
            "Evaluates AICPA SOC 2 Trust Services Criteria (CC6.1 Logical Access, CC7.2 Anomaly Detection, "
            "CC8.1 Change Management) across GitHub branch protection rules, AWS KMS customer-managed key "
            "rotation, Okta phishing-resistant MFA enforcement, and production audit log retention."
        ),
        "frameworks": ["AICPA SOC 2 Type II", "ISO 27001:2022", "HIPAA 164.312"],
        "input_type": "soc2_evidence_snapshot",
        "cli_flags": [
            "--evidence-file",
            "--audit-period",
            "--min-approvals",
            "--output-format",
        ],
        "guardrails": [
            "Never fabricates compliance evidence; every PASS/FAIL control decision links to an immutable evidence ID.",
            "Requires >= 2 independent code review approvals and signed commits on production branches for CC8.1.",
            "Outputs cryptographic SHA-256 evidence digest for external auditor verification.",
        ],
        "rules": [
            {
                "rule_id": "SOC2-CC6.1",
                "title": "Identity Provider Phishing-Resistant MFA Enforcement",
                "severity": "CRITICAL",
                "control": "SOC 2 CC6.1 / ISO 27001 A.8.5",
                "check": "mfa_enforcement_gap",
                "remediation": "Enforce WebAuthn/FIDO2 MFA for 100% of human identities in Okta/OIDC policy.",
            },
            {
                "rule_id": "SOC2-CC6.7",
                "title": "Customer-Managed KMS Key Automatic Rotation Disabled",
                "severity": "HIGH",
                "control": "SOC 2 CC6.7 / NIST SC-12",
                "check": "kms_rotation_disabled",
                "remediation": "Enable annual automatic key rotation on all production KMS CMKs.",
            },
            {
                "rule_id": "SOC2-CC7.2",
                "title": "Centralized SIEM Log Retention Below 365-Day Requirement",
                "severity": "HIGH",
                "control": "SOC 2 CC7.2",
                "check": "log_retention_shortfall",
                "remediation": "Configure immutable S3 Object Lock / SIEM retention to >= 365 days.",
            },
            {
                "rule_id": "SOC2-CC8.1",
                "title": "GitHub Main Branch Missing Required Reviews or Status Checks",
                "severity": "HIGH",
                "control": "SOC 2 CC8.1",
                "check": "weak_branch_protection",
                "remediation": "Require at least 2 approving PR reviews, dismiss stale reviews, and enforce CI status checks.",
            },
        ],
        "sample_input": {
            "organization": "acme-cloud-corp",
            "audit_period": "2026-Q4",
            "controls_evidence": [
                {
                    "asset_id": "okta-prod-tenant",
                    "asset_type": "identity_provider",
                    "mfa_enforced_pct": 94.5,
                    "kms_rotation_enabled": True,
                    "log_retention_days": 400,
                    "required_pr_approvals": 2,
                    "signed_commits_required": True,
                },
                {
                    "asset_id": "github-repo-billing-service",
                    "asset_type": "source_repository",
                    "mfa_enforced_pct": 100.0,
                    "kms_rotation_enabled": False,
                    "log_retention_days": 90,
                    "required_pr_approvals": 1,
                    "signed_commits_required": False,
                },
            ],
        },
    },
    "gdpr-pii-dataflow-lineage-scanner": {
        "id": "gdpr-pii-dataflow-lineage-scanner",
        "name": "gdpr-pii-dataflow-lineage-scanner",
        "title": "GDPR & CCPA PII Dataflow Lineage & Encryption Scanner",
        "category": "Data Privacy (GDPR / CCPA / HIPAA)",
        "version": "1.1.0",
        "description": (
            "Scans OpenAPI 3.1 payloads, PostgreSQL/Snowflake DDL schemas, and ETL sink configurations "
            "for unencrypted PII/PHI columns, missing data retention TTLs, unmasked analytics logging, "
            "and unapproved cross-border transfers under GDPR Articles 25, 30, 32, and 44."
        ),
        "frameworks": ["GDPR Art. 25/30/32/44", "CCPA/CPRA", "HIPAA Safe Harbor"],
        "input_type": "data_lineage_manifest",
        "cli_flags": [
            "--lineage-file",
            "--allowed-regions",
            "--require-column-encryption",
            "--output-format",
        ],
        "guardrails": [
            "Inspects schema metadata and lineage configurations only; never extracts or stores raw customer PII records.",
            "Flags any high-sensitivity PII/PHI column lacking column-level AEAD encryption or tokenization.",
            "Verifies GDPR Article 17 right-to-erasure TTL policies on all downstream tables.",
        ],
        "rules": [
            {
                "rule_id": "GDPR-032",
                "title": "PII/PHI Column Stored Without Field-Level Encryption or Tokenization",
                "severity": "CRITICAL",
                "control": "GDPR Art. 32(1)(a)",
                "check": "unencrypted_pii_column",
                "remediation": "Apply deterministic AEAD column encryption or format-preserving tokenization before storage.",
            },
            {
                "rule_id": "GDPR-025",
                "title": "Dataset Missing Automated Retention TTL / Erasure Policy",
                "severity": "HIGH",
                "control": "GDPR Art. 25 & Art. 17",
                "check": "missing_retention_ttl",
                "remediation": "Configure automated partition expiration or scheduled erasure job <= 365 days.",
            },
            {
                "rule_id": "GDPR-044",
                "title": "Cross-Border EU Data Sink Outside Approved Sovereign Regions",
                "severity": "HIGH",
                "control": "GDPR Art. 44",
                "check": "unapproved_cross_border_sink",
                "remediation": "Pin EU subject data stores to eu-central-1 / eu-west-1 or enforce Standard Contractual Clauses with BYOK.",
            },
            {
                "rule_id": "GDPR-030",
                "title": "PII Field Exposed in Unredacted Application Telemetry Logs",
                "severity": "MEDIUM",
                "control": "GDPR Art. 30 / SOC 2 CC6.1",
                "check": "pii_in_application_logs",
                "remediation": "Add OpenTelemetry attribute redaction filter to strip email, ssn, and tax_id before export.",
            },
        ],
        "sample_input": {
            "controller": "eu-fintech-platform",
            "approved_eu_regions": ["eu-central-1", "eu-west-1"],
            "datasets": [
                {
                    "dataset_name": "postgres.public.customer_kyc_profiles",
                    "region": "us-east-1",
                    "eu_data_subjects": True,
                    "retention_ttl_days": None,
                    "redacted_in_logs": False,
                    "columns": [
                        {"name": "customer_id", "pii_category": "identifier", "encrypted": True},
                        {"name": "national_tax_id", "pii_category": "government_id", "encrypted": False},
                        {"name": "email_address", "pii_category": "contact", "encrypted": False},
                    ],
                },
                {
                    "dataset_name": "snowflake.eu_core.tokenized_transactions",
                    "region": "eu-central-1",
                    "eu_data_subjects": True,
                    "retention_ttl_days": 180,
                    "redacted_in_logs": True,
                    "columns": [
                        {"name": "tx_id", "pii_category": "none", "encrypted": True},
                        {"name": "iban_token", "pii_category": "financial", "encrypted": True},
                    ],
                },
            ],
        },
    },
    "openapi-idor-authz-triage-engine": {
        "id": "openapi-idor-authz-triage-engine",
        "name": "openapi-idor-authz-triage-engine",
        "title": "OpenAPI 3.1 IDOR & Source-to-Sink Authorization Triage Engine",
        "category": "Application Security (OWASP API Top 10)",
        "version": "1.4.0",
        "description": (
            "Performs multi-gate source-to-sink authorization verification across OpenAPI 3.1 route "
            "specifications, OAuth2/OIDC JWT scope definitions, and backend object-level ownership "
            "guards to separate exploitable True Positive BOLA/IDOR vulnerabilities from mitigated False Positives."
        ),
        "frameworks": ["OWASP API Security Top 10 (API1:2023)", "CWE-639", "NIST 800-53 AC-3"],
        "input_type": "openapi_route_matrix",
        "cli_flags": [
            "--openapi-spec",
            "--verify-ownership-guard",
            "--fail-on-true-positive",
            "--output-format",
        ],
        "guardrails": [
            "Static contract & AST guard analysis only; never sends destructive fuzzing payloads to production endpoints.",
            "Distinguishes authentication (valid JWT) from object-level authorization (tenant_id / owner_id predicate).",
            "Classifies routes with verified middleware ownership checks as Mitigated False Positives to eliminate alert fatigue.",
        ],
        "rules": [
            {
                "rule_id": "API1-001",
                "title": "Broken Object Level Authorization (BOLA / IDOR) on Path Parameter Route",
                "severity": "CRITICAL",
                "control": "OWASP API1:2023 / CWE-639",
                "check": "bola_missing_ownership_check",
                "remediation": "Enforce tenant_id/owner_id predicate in SQL WHERE clause bound to verified JWT sub claim.",
            },
            {
                "rule_id": "API5-002",
                "title": "State-Mutating Admin/Write Route Missing OAuth2 Scope Constraint",
                "severity": "HIGH",
                "control": "OWASP API5:2023 / CWE-285",
                "check": "mutating_route_missing_scope",
                "remediation": "Require explicit fine-grained OAuth2 scope (e.g., 'invoices:write' or 'admin:Write') in route security scheme.",
            },
            {
                "rule_id": "API2-003",
                "title": "Publicly Exposed Endpoint Accepting Object ID Without Authentication",
                "severity": "CRITICAL",
                "control": "OWASP API2:2023",
                "check": "unauthenticated_object_route",
                "remediation": "Attach BearerAuth OIDC security scheme and reject anonymous requests with HTTP 401.",
            },
            {
                "rule_id": "API8-004",
                "title": "Bulk Export Endpoint Missing Rate Limit & Pagination Ceiling",
                "severity": "MEDIUM",
                "control": "OWASP API4:2023",
                "check": "unbounded_bulk_export",
                "remediation": "Enforce token-bucket rate limiting and cap page_size <= 100 records per request.",
            },
        ],
        "sample_input": {
            "service_name": "b2b-invoicing-gateway",
            "openapi_version": "3.1.0",
            "routes": [
                {
                    "path": "/v1/organizations/{org_id}/invoices/{invoice_id}",
                    "method": "DELETE",
                    "auth_required": True,
                    "required_scopes": [],
                    "has_path_object_id": True,
                    "db_ownership_predicate_verified": False,
                    "rate_limit_configured": False,
                },
                {
                    "path": "/v1/public/Exports/{export_id}",
                    "method": "GET",
                    "auth_required": False,
                    "required_scopes": [],
                    "has_path_object_id": True,
                    "db_ownership_predicate_verified": False,
                    "rate_limit_configured": False,
                },
                {
                    "path": "/v1/organizations/{org_id}/ledger/{entry_id}",
                    "method": "GET",
                    "auth_required": True,
                    "required_scopes": ["ledger:read"],
                    "has_path_object_id": True,
                    "db_ownership_predicate_verified": True,
                    "rate_limit_configured": True,
                },
            ],
        },
    },
    "finops-cloud-cost-anomaly-detector": {
        "id": "finops-cloud-cost-anomaly-detector",
        "name": "finops-cloud-cost-anomaly-detector",
        "title": "Cloud FinOps Waste, Idle GPU & Cost Anomaly Detector",
        "category": "Cloud FinOps & Infrastructure Efficiency",
        "version": "1.1.0",
        "description": (
            "Analyzes Terraform HCL resource inventories, Kubernetes node pools, and cloud billing "
            "telemetry to identify unattached EBS/persistent volumes, underutilized GPU instances "
            "(<15% utilization), unassociated elastic IPs, and rightsizing savings opportunities."
        ),
        "frameworks": ["FinOps Foundation Framework", "AWS Well-Architected Cost Optimization"],
        "input_type": "finops_telemetry_bundle",
        "cli_flags": [
            "--telemetry-file",
            "--gpu-util-threshold",
            "--min-monthly-savings-usd",
            "--output-format",
        ],
        "guardrails": [
            "Generates deterministic rightsizing and snapshot-before-delete recommendations; never terminates instances directly.",
            "Calculates exact monthly and annualized USD savings based on resource hourly unit rates.",
            "Preserves stateful production volumes unless explicitly tagged as orphaned for > 14 days.",
        ],
        "rules": [
            {
                "rule_id": "FIN-001",
                "title": "Underutilized GPU / Accelerated Compute Node (<15% 14-Day Avg Utilization)",
                "severity": "HIGH",
                "control": "FinOps Compute Rightsizing",
                "check": "idle_gpu_instance",
                "remediation": "Downsize instance family or migrate batch inference workload to spot/autoscale node group.",
            },
            {
                "rule_id": "FIN-002",
                "title": "Unattached Block Storage Volume Orphaned > 14 Days",
                "severity": "MEDIUM",
                "control": "FinOps Storage Lifecycle",
                "check": "unattached_ebs_volume",
                "remediation": "Take final encrypted snapshot and delete unattached EBS/PD volume.",
            },
            {
                "rule_id": "FIN-003",
                "title": "On-Demand Steady-State Production Compute Without Savings Plan / RI Coverage",
                "severity": "MEDIUM",
                "control": "FinOps Rate Optimization",
                "check": "uncommitted_steady_compute",
                "remediation": "Purchase 1-year No-Upfront Compute Savings Plan to capture 28-42% discount.",
            },
            {
                "rule_id": "FIN-004",
                "title": "Production Resource Missing Mandatory Cost Allocation Tags (cost_center, owner)",
                "severity": "LOW",
                "control": "FinOps Cost Allocation",
                "check": "missing_finops_tags",
                "remediation": "Apply mandatory cost_center, environment, and service_owner tags in Terraform default_tags.",
            },
        ],
        "sample_input": {
            "billing_account": "finops-prod-master",
            "currency": "USD",
            "resources": [
                {
                    "resource_id": "i-0a9f8b7c6d5e4f3a2",
                    "resource_type": "aws_instance_p4d_24xlarge",
                    "monthly_cost_usd": 23950.0,
                    "avg_utilization_pct": 6.4,
                    "attached": True,
                    "days_unattached": 0,
                    "savings_plan_covered": False,
                    "has_cost_tags": False,
                },
                {
                    "resource_id": "vol-09911882277336655",
                    "resource_type": "aws_ebs_gp3_4tb",
                    "monthly_cost_usd": 327.68,
                    "avg_utilization_pct": 0.0,
                    "attached": False,
                    "days_unattached": 39,
                    "savings_plan_covered": False,
                    "has_cost_tags": True,
                },
                {
                    "resource_id": "i-01122334455667788",
                    "resource_type": "aws_instance_m7i_2xlarge",
                    "monthly_cost_usd": 294.3,
                    "avg_utilization_pct": 78.2,
                    "attached": True,
                    "days_unattached": 0,
                    "savings_plan_covered": True,
                    "has_cost_tags": True,
                },
            ],
        },
    },
}


def list_presets() -> List[Dict[str, Any]]:
    """Return all built-in presets in deterministic order."""
    ordered_ids = [
        "aws-iam-least-privilege-auditor",
        "k8s-zero-trust-network-verifier",
        "soc2-continuous-control-monitor",
        "gdpr-pii-dataflow-lineage-scanner",
        "openapi-idor-authz-triage-engine",
        "finops-cloud-cost-anomaly-detector",
    ]
    return [PRESETS[k] for k in ordered_ids if k in PRESETS]


def get_preset(preset_id: str) -> Dict[str, Any]:
    """Retrieve a single preset by ID."""
    if preset_id not in PRESETS:
        raise KeyError(f"Unknown preset '{preset_id}'. Available: {', '.join(PRESETS.keys())}")
    return PRESETS[preset_id]
