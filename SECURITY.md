# Security policy

## Supported versions

Security fixes currently target the default branch. The first immutable
release will introduce an explicit supported-version table.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting channel for this repository when
it is available. If the channel is unavailable, contact the maintainer through
the address recorded in the repository owner's verified GitHub profile. Keep
exploit details out of public issues.

Include:

- the affected commit or version;
- the input and execution path that reaches the issue;
- the expected and observed behavior;
- the impact on certificate verification, resource limits, artifact integrity,
  or native execution; and
- a minimal reproduction when disclosure is safe.

Receipt should be acknowledged within seven days. Triage establishes affected
versions, severity, disclosure timing, and whether research artifacts require
revalidation. A fix that changes a serialized contract receives a new
versioned identifier and migration note.

## Research-integrity reports

Incorrect mathematical claims, invalid certificates, leakage, provenance
breaks, and irreproducible evidence can be reported through the
research-validity issue form. Security-sensitive details use the private
channel. Identify the affected claim, protocol, and artifact digest.
