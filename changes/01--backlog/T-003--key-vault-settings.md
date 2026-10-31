# T-003 Secrets from the Key Vault in settings

## Problem

`commons.settings` reads settings only from TOML files and `APP__*` environment variables. In Azure, secrets therefore reach an app as plain app settings: the deployment (`sandbox_app` of `core--terraform-modules`) reads them from the Key Vault and copies their values into the App Service configuration and the OpenTofu state, and an app has no way to get secrets of its own. Found in T-003 of `core--platform`, which notes the platform side as its T-006.

## Proposed outcome

- `commons.settings` reads secrets from an Azure Key Vault as one more settings layer, as Spring Cloud Azure and ASP.NET Core do: settings files, then Key Vault, then `APP__*` environment variables (later wins).
- Naming: `<prefix>--<key>--<key>`, where `--` stands for `__` and `-` for `_` (`APP__DATABASE__MSSQL__PASSWORD` ↔ `hello--database--mssql--password`). Secrets of the prefix `shared--` are loaded first, the app's own prefix overrides them. One vault per stage; the stage isn't part of the name.
- Enabled by the settings `key_vault.url` and `key_vault.prefix` (`APP__KEY_VAULT__URL`, `APP__KEY_VAULT__PREFIX`); without a URL the layer is skipped, as in local development. Loaded once, with the merged settings; a rotated secret takes effect after a restart.
- Signed in with `DefaultAzureCredential` (managed identity in Azure, `az login` locally), through the extra `azure` (`azure-identity` is there; `azure-keyvault-secrets` is added).
