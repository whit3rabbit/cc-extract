# Claude Code Router Support

cc-extractor supports Claude Code Router through the `ccrouter` provider. The
default mode is managed and isolated: cc-extractor installs CCR inside the
setup, creates a setup-local home directory, copies or seeds CCR config, starts
CCR on demand, and runs the patched Claude Code binary directly.

## Managed CCR

Create a managed setup:

```bash
cc-extractor variant create --name ccrouter --provider ccrouter
```

Managed files live under the setup:

```text
.cc-extractor/variants/<setup-id>/ccr-runtime/
.cc-extractor/variants/<setup-id>/ccr-home/.claude-code-router/config.json
.cc-extractor/variants/<setup-id>/tmp/ccrouter.log
```

Important behavior:

- `HOME` and `USERPROFILE` are set to the setup-local `ccr-home` before running
  `ccr`, so CCR reads and writes setup-local config.
- `@musistudio/claude-code-router` is installed locally with npm under
  `ccr-runtime`; no global npm install is required.
- If the real `~/.claude-code-router/config.json` exists, managed create uses
  `copy-global` by default. The copy is one-time and not a symlink.
- If no global config exists, managed create uses `empty` and writes a minimal
  config with `PORT`, `Providers`, and `Router`.
- The copied or seeded config gets a setup-specific local port unless
  `--ccrouter-port` is supplied.
- The wrapper starts `ccr start` when auto-start is enabled, parses the isolated
  config safely, exports the Anthropic-compatible CCR endpoint, and then execs
  the cc-extractor patched Claude binary. It does not call `ccr code`.

Useful create options:

```bash
cc-extractor variant create --name ccrouter --provider ccrouter --ccrouter-config empty
cc-extractor variant create --name ccrouter --provider ccrouter --ccrouter-config copy-global
cc-extractor variant create --name ccrouter --provider ccrouter --ccrouter-package @musistudio/claude-code-router@2.0.0
cc-extractor variant create --name ccrouter --provider ccrouter --ccrouter-port 4567
cc-extractor variant create --name ccrouter --provider ccrouter --no-ccrouter-autostart
```

Use `variant doctor` to check the wrapper, config, local `ccr` install, Node
version, and CCR running state:

```bash
cc-extractor variant doctor ccrouter
```

## External CCR

Use external mode when you intentionally want to manage a global CCR service
yourself:

```bash
npm install -g @musistudio/claude-code-router
# edit ~/.claude-code-router/config.json
ccr start
cc-extractor variant create --name ccrouter --provider ccrouter --ccrouter-mode external
```

In external mode, cc-extractor keeps the old behavior: the setup points Claude
Code at `http://127.0.0.1:3456` unless you override the endpoint, and
cc-extractor does not install or start CCR.

## TUI Notes

The setup wizard shows managed CCR options on the credentials step when the
`ccrouter` provider is selected:

- managed or external mode;
- config source (`copy-global`, `empty`, or `shared-home`);
- npm package spec;
- port (`auto` or a number);
- auto-start toggle.

After creating a managed CCR setup, the setup detail screen shows CCR metadata
and actions for status, start, stop, restart, UI, and copying the setup-local
CCR config path.

## Architect Model Proxy

`--model-proxy architect` is separate from CCR. It starts a setup-local
Anthropic-compatible proxy that can route non-Claude model aliases to the
provider backend while preserving Claude model calls for Claude Code.

This mode requires a Claude Code account. The proxy forwards Claude model calls
to Anthropic using the user's normal Claude Code OAuth/session path, and sends
non-Claude model calls to the configured provider backend using the provider
credential. That means the setup still needs a valid Claude Code login for
Claude-owned requests, even when worker models are routed elsewhere.

Create with architect proxy:

```bash
cc-extractor variant create \
  --name architect-proxy \
  --provider zai \
  --credential-env Z_AI_API_KEY \
  --model-proxy architect
```

Rules:

- `--model-proxy` only accepts `architect`.
- The provider must have backend credentials.
- `--model-opus` must stay a `claude-*` model, because Opus/architect calls
  are kept on Claude.
- Worker/default model aliases can point at backend models.
- The wrapper starts the proxy for the lifetime of the setup command and stops
  it on exit.
