"""
Create an Azure AI Search index and upload the sample product-literature docs
(foundry/knowledge/*.md) so they can be used as a Foundry IQ knowledge source.

Environment (from repo .env):
    AI_SEARCH_ENDPOINT   e.g. https://<name>.search.windows.net
    AI_SEARCH_INDEX      index name (default 'telco-knowledge')

Auth: uses DefaultAzureCredential (run 'az login' with a principal that has the
Search Service Contributor + Search Index Data Contributor roles).

This creates a simple keyword/semantic index (id, title, content, source). Add vector
embeddings later if you want vector/hybrid retrieval.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
KNOWLEDGE = HERE / "knowledge"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> int:
    load_env_file(REPO / ".env")
    endpoint = os.environ.get("AI_SEARCH_ENDPOINT")
    index_name = os.environ.get("AI_SEARCH_INDEX", "telco-knowledge")
    if not endpoint:
        print("ERROR: AI_SEARCH_ENDPOINT not set (run infra/deploy.ps1 first).", file=sys.stderr)
        return 1

    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchableField, SearchField, SearchFieldDataType, SimpleField, SearchIndex,
        SemanticConfiguration, SemanticField, SemanticPrioritizedFields, SemanticSearch,
    )

    # Auth: prefer an admin API key (AI_SEARCH_ADMIN_KEY) so no data-plane RBAC/AAD setup is
    # needed on the search service; fall back to Entra (DefaultAzureCredential).
    admin_key = os.environ.get("AI_SEARCH_ADMIN_KEY")
    if admin_key:
        from azure.core.credentials import AzureKeyCredential
        cred = AzureKeyCredential(admin_key)
        print("Authenticating to AI Search with admin key.")
    else:
        from azure.identity import DefaultAzureCredential
        cred = DefaultAzureCredential()
        print("Authenticating to AI Search with Entra credential "
              "(set AI_SEARCH_ADMIN_KEY to use a key instead).")

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
    ]
    semantic = SemanticSearch(configurations=[SemanticConfiguration(
        name="default",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="title"),
            content_fields=[SemanticField(field_name="content")],
        ),
    )])
    index = SearchIndex(name=index_name, fields=fields, semantic_search=semantic)

    idx_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    idx_client.create_or_update_index(index)
    print(f"Index '{index_name}' created/updated.")

    docs = []
    for i, md in enumerate(sorted(KNOWLEDGE.glob("*.md"))):
        text = md.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else md.stem
        docs.append({"id": f"doc{i}", "title": title, "content": text, "source": md.name})

    if not docs:
        print("No knowledge docs found to upload.")
        return 0

    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)
    result = search_client.upload_documents(documents=docs)
    ok = sum(1 for r in result if r.succeeded)
    print(f"Uploaded {ok}/{len(docs)} documents to '{index_name}'.")
    print("Next: create an AI Search connection in the Foundry project and set "
          "AI_SEARCH_CONNECTION_NAME + AI_SEARCH_INDEX in .env, then re-run deploy_agents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
