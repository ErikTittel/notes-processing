<!--
Sync Impact Report
Version change: not established -> 1.0.0 (initial constitution)
Modified principles:
- Template principle slot 1 -> I. Local-Only Operation
- Template principle slot 2 -> II. Windows and OneNote COM
- Template principle slot 3 -> III. Safe Reorganization
- Template principle slot 4 -> IV. Predictable, User-Visible Changes
- Template principle slot 5 -> V. Testability and Simplicity
Added sections: Platform and Data Constraints; Development Workflow
Removed sections: none
Follow-up TODO: Confirm the original ratification date.
-->

# notes-processing Constitution

## Core Principles

### I. Local-Only Operation
The application MUST run without internet access. It MUST NOT send notes, metadata,
diagnostics, or usage data to remote services, and its normal operation MUST NOT depend
on network access. This keeps private notes under the user's local control.

### II. Windows and OneNote COM
The application MUST target Windows and access OneNote through the OneNote-COM-API.
OneNote interactions MUST be isolated behind clear boundaries, and COM failures MUST
be surfaced to the user rather than treated as successful operations.

### III. Safe Reorganization
Reorganization MUST preserve note content and unrelated OneNote data. The application
MUST identify the intended changes before applying them and MUST obtain explicit user
confirmation before an irreversible change. When an operation fails, it MUST report
the failure and avoid claiming that unapplied changes succeeded.

### IV. Predictable, User-Visible Changes
The same input and OneNote state MUST produce the same planned reorganization. The
application MUST make its actions and affected notes understandable to the user, and
MUST NOT silently skip, broaden, or reinterpret a requested operation.

### V. Testability and Simplicity
Core reorganization logic MUST be testable independently of a live OneNote instance.
Changes MUST include focused tests for their behavior, with COM integration tests
added when behavior depends on OneNote itself. Implementations MUST prefer the
simplest design that satisfies the requirements.

## Platform and Data Constraints

The project is a Python application for local use on Windows. OneNote MUST be installed
and accessible through its COM API for operations that interact with notebooks. The
application MUST keep note processing local and MUST NOT introduce a network service
or an internet-dependent runtime requirement.

## Development Workflow

Changes MUST be validated with relevant automated tests before integration. Tests for
core organization rules MUST NOT require real user notebooks. Changes to COM behavior
MUST also receive an integration check when a suitable local OneNote environment is
available. Reviews MUST verify compliance with this constitution and confirm that
user data is not exposed or unintentionally altered.

## Governance

This constitution governs project decisions and supersedes conflicting project
guidance. The project maintainer MUST review and approve amendments. An amendment
proposal MUST describe its rationale, affected principles, compatibility impact, and
any required follow-up work. Changes that alter application behavior MUST identify
relevant tests or validation steps.

The constitution uses semantic versioning. A MAJOR increment marks a backward-
incompatible change to governance or a redefinition/removal of a principle. A MINOR
increment marks a new principle or section, or materially expanded requirements. A
PATCH increment marks clarifications and non-semantic refinements. Every amendment
MUST update the version and last-amended date.

Maintainers and reviewers MUST assess compliance with this constitution when reviewing
changes. Any exception MUST be explicit, justified, and approved by the project
maintainer; persistent exceptions MUST be incorporated through a constitution
amendment.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): confirm original adoption date | **Last Amended**: 2026-11-07
