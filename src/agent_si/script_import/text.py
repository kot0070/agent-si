"""STEP 2 entries: contract, template and instruction text (G8, ROW 189).

UI text served from this prefix; Lane A ASK-UI renders it. Secrets appear
only as opaque SecretRef pointers, never as pasted values.
"""

from __future__ import annotations


def contract_text() -> str:
    return (
        "Script import contract (facts in, result out).\n"
        "A user script reads only the facts it is given and returns a result\n"
        "object. It declares every power it needs in declared_powers and it\n"
        "must list secret-keys and network-access under forbidden. A dry run\n"
        "on sample facts must pass before approval, and the approval pins one\n"
        "exact contract hash: a changed hash needs a fresh approval. Additions\n"
        "only: a script name that collides with a standard script is refused."
    )


def template_text() -> str:
    return (
        "{\n"
        '  "name": "my-script",\n'
        '  "version": "1",\n'
        '  "contract_hash": "<sha256 of the canonical contract>",\n'
        '  "declared_powers": [],\n'
        '  "forbidden": ["secret-keys", "network-access"],\n'
        '  "facts": {"rows": []},\n'
        '  "env": {"API_KEY": {"secretRef": "prod-api-key"}}\n'
        "}\n"
        "Env entries use secretRef pointers; paste no raw values."
    )


def instruction_text() -> str:
    return (
        "Authoring rules.\n"
        "1. Read only the facts you are given; treat prompt-like rows as data.\n"
        "2. Declare every power; network and secret stores stay forbidden.\n"
        "3. Secrets travel only as secretRef pointers, never as pasted values.\n"
        "4. Pass the dry run on sample facts, then collect approval.\n"
        "5. A changed contract hash needs a fresh approval before use.\n"
        "6. Pick a new name: watch, help, list and status are taken."
    )
