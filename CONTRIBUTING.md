# Contributing

Measurements are submitted from DSR SPL Reference through the DSR HTTPS contribution service. No GitHub account is required. The service reserves a deterministic `submission/<uuid>` branch and draft pull request, derives the public ID from the PR number, and leaves merge decisions to DSR curators.

Contributors must review the complete public payload, confirm submission under CC BY 4.0, and, if applicable, confirm rights to publish the sanitized photo derivative. Projects, coordinates, excluded notes/photos and original photo metadata are prohibited. Pull requests must pass `validate-contribution`.

Contribution pull requests contain only canonical record, registry and optional photo files whose paths are unique to that submission. They do not edit a shared index; the protected Pages build publishes the generated CSV from canonical records after each merge.

Repository administrators should protect `main`: require a pull request, require the `validate-contribution` status check, require conversation resolution, disallow force pushes and direct service writes, and do not let the submission GitHub App bypass protection. The App needs only Metadata read, Contents read/write, and Pull requests read/write on this repository.
