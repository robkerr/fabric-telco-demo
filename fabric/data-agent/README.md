# Fabric Data Agent

The Data Agent is created by **running a Fabric notebook**, not from your local workstation. The
SDK depends on the Fabric runtime and .NET interop (`sempy`/`pythonnet`), which isn't supported
off-cluster and does not work on ARM64 Windows.

## How to create/publish it

1. Run `scripts/10_provision_fabric.ps1` (once) - it uploads the **`05_create_data_agent`**
   notebook into your workspace along with the medallion notebooks.
2. In Fabric, open **`05_create_data_agent`**, attach the **TelcoLakehouse** as the default
   Lakehouse, and **Run all**.
3. Copy the printed `DATA_AGENT_ARTIFACT_ID` and `DATA_AGENT_MCP_ENDPOINT` into your local `.env`
   (the Foundry agents bind to these in Phase 3).

## Source of truth

[`config.yaml`](config.yaml) defines the agent name, description, AI instructions, the Lakehouse
datasource, and the per-journey example queries. `fabric/notebooks/build_notebooks.py` embeds it
into the `05_create_data_agent` notebook when the notebooks are (re)built:

```powershell
python fabric/notebooks/build_notebooks.py         # regenerate the .ipynb files
./scripts/10_provision_fabric.ps1 -SkipUpload      # re-import the updated notebook
```

Then re-run the notebook in Fabric to update and re-publish the agent.
