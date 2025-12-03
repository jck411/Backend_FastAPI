<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { get } from "svelte/store";
  import { createGoogleAuthStore } from "../../stores/googleAuth";
  import { createMcpServersStore } from "../../stores/mcpServers";
  import { createMonarchAuthStore } from "../../stores/monarchAuth";
  import { createSpotifyAuthStore } from "../../stores/spotifyAuth";
  import { createSystemPromptStore } from "../../stores/systemPrompt";
  import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";
  import "./system-settings.css";

  export let open = false;

  const dispatch = createEventDispatcher<{ close: void }>();
  const systemPrompt = createSystemPromptStore();
  const mcpServers = createMcpServersStore();
  const googleAuth = createGoogleAuthStore();
  const monarchAuth = createMonarchAuthStore();
  const spotifyAuth = createSpotifyAuthStore();

  let hasInitialized = false;
  let closing = false;
  let expandedServers: Set<string> = new Set();

  $: {
    if (open && !hasInitialized) {
      hasInitialized = true;
      void initialize();
    } else if (!open && hasInitialized) {
      hasInitialized = false;
      systemPrompt.reset();
      googleAuth.reset();
      spotifyAuth.reset();
    }
  }

  async function initialize(): Promise<void> {
    await Promise.all([
      systemPrompt.load(),
      mcpServers.load(),
      googleAuth.load(),
      monarchAuth.load(),
      spotifyAuth.load(),
    ]);
  }

  async function flushSystemPrompt(): Promise<boolean> {
    const state = get(systemPrompt);
    if (!state.dirty) {
      return true;
    }
    await systemPrompt.save();
    const latest = get(systemPrompt);
    return !latest.saveError;
  }

  async function closeModal(): Promise<void> {
    if (closing || $systemPrompt.saving || $mcpServers.saving) {
      return;
    }

    closing = true;

    const promptSaved = await flushSystemPrompt();
    const serversSaved = promptSaved ? await mcpServers.flushPending() : false;

    const promptState = get(systemPrompt);
    const serversState = get(mcpServers);

    if (
      promptSaved &&
      serversSaved &&
      !promptState.saveError &&
      !serversState.saveError
    ) {
      dispatch("close");
    }

    closing = false;
  }

  let monarchEmail = "";
  let monarchPassword = "";
  let monarchMfaSecret = "";
  let showMonarchPassword = false;
  let showShellPassword = false;

  function saveMonarch(): void {
    if (!monarchEmail || !monarchPassword) return;
    monarchAuth.save({
      email: monarchEmail,
      password: monarchPassword,
      mfa_secret: monarchMfaSecret || null,
    });
  }

  function handlePromptInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement | null;
    systemPrompt.updateValue(target?.value ?? "");
  }

  function toggleServer(serverId: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setServerEnabled(serverId, enabled);
  }

  function toggleTool(serverId: string, tool: string, enabled: boolean): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setToolEnabled(serverId, tool, enabled);
  }

  function handleShellEnv(serverId: string, key: string, value: string): void {
    if ($mcpServers.saving) {
      return;
    }
    mcpServers.setServerEnv(serverId, key, value);
  }

  function isShellApprovalEnabled(env?: Record<string, string>): boolean {
    const raw = env?.REQUIRE_APPROVAL ?? "true";
    return String(raw).toLowerCase() === "true";
  }

  function refreshServers(): void {
    const snapshot = get(mcpServers);
    if (snapshot.dirty || snapshot.saving) {
      return;
    }
    void mcpServers.refresh();
  }

  function refreshGoogleAuth(): void {
    if ($googleAuth.loading || $googleAuth.authorizing) {
      return;
    }
    void googleAuth.load();
  }

  async function startGoogleAuthorization(): Promise<void> {
    if ($googleAuth.authorizing) {
      return;
    }
    await googleAuth.authorize();
  }

  function refreshSpotifyAuth(): void {
    if ($spotifyAuth.loading || $spotifyAuth.authorizing) {
      return;
    }
    void spotifyAuth.load();
  }

  async function startSpotifyAuthorization(): Promise<void> {
    if ($spotifyAuth.authorizing) {
      return;
    }
    await spotifyAuth.authorize();
  }

  function formatUpdatedAt(timestamp: string | null): string | null {
    if (!timestamp) return null;
    try {
      const date = new Date(timestamp);
      if (Number.isNaN(date.getTime())) {
        return timestamp;
      }
      return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        year: "numeric",
        month: "short",
        day: "2-digit",
      }).format(date);
    } catch (error) {
      console.warn("Failed to format timestamp", error);
      return timestamp;
    }
  }

  function toggleServerTools(serverId: string): void {
    const newExpanded = new Set(expandedServers);
    if (newExpanded.has(serverId)) {
      newExpanded.delete(serverId);
    } else {
      newExpanded.add(serverId);
    }
    expandedServers = newExpanded;
  }
</script>

{#if open}
  <ModelSettingsDialog
    {open}
    labelledBy="system-settings-title"
    modalClass="system-settings-modal"
    bodyClass="system-settings-body"
    layerClass="system-settings-layer"
    closeLabel="Close system settings"
    closeDisabled={$systemPrompt.saving ||
      $mcpServers.saving ||
      $googleAuth.authorizing}
    on:close={() => void closeModal()}
  >
    <svelte:fragment slot="heading">
      <h2 id="system-settings-title">System settings</h2>
      <p class="model-settings-subtitle">
        Configure orchestration defaults and MCP servers.
      </p>
    </svelte:fragment>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>System prompt</h3>
          <p class="system-card-caption">
            Applied to new chat sessions when no custom prompt is present.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="ghost"
            on:click={() => systemPrompt.reset()}
            disabled={!$systemPrompt.dirty ||
              $systemPrompt.saving ||
              $mcpServers.saving}
          >
            Reset
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $systemPrompt.loading}
          <p class="status">Loading system prompt…</p>
        {:else if $systemPrompt.error}
          <p class="status error">{$systemPrompt.error}</p>
        {:else}
          <textarea
            class="system-prompt"
            rows="6"
            bind:value={$systemPrompt.value}
            on:input={handlePromptInput}
            placeholder="Provide guidance for the assistant to follow at the start of new conversations."
            disabled={$systemPrompt.saving}
          ></textarea>
          {#if $systemPrompt.saveError}
            <p class="status error">{$systemPrompt.saveError}</p>
          {:else if $systemPrompt.dirty}
            <p class="status">Pending changes; closing this modal will save.</p>
          {:else}
            <p class="status muted">Changes save when you close this modal.</p>
          {/if}
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Google services</h3>
          <p class="system-card-caption">
            Connect Calendar, Tasks, Gmail, and Drive with a single consent.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="primary"
            on:click={() => void startGoogleAuthorization()}
            disabled={$googleAuth.loading || $googleAuth.authorizing}
          >
            {$googleAuth.authorizing
              ? "Authorizing…"
              : $googleAuth.authorized
                ? "Reconnect Google Services"
                : "Connect Google Services"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $googleAuth.loading}
          <p class="status">Checking Google authorization…</p>
        {:else if $googleAuth.error}
          <p class="status error">{$googleAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="ghost"
              on:click={refreshGoogleAuth}
              disabled={$googleAuth.loading || $googleAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $googleAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$googleAuth.userEmail}</span
            >.
          </p>
          {#if $googleAuth.expiresAt}
            <p class="status muted">
              Current token expires {formatUpdatedAt($googleAuth.expiresAt) ??
                "soon"}.
            </p>
          {:else}
            <p class="status muted">Access will refresh automatically.</p>
          {/if}
        {:else}
          <p class="status">Google services are not connected.</p>
        {/if}

        <ul class="google-services-list">
          {#each $googleAuth.services as service}
            <li>{service}</li>
          {/each}
        </ul>

        <p class="status muted">
          Click "Connect Google Services" to authorize these integrations for
          the assistant.
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Spotify</h3>
          <p class="system-card-caption">
            Connect Spotify for music control and playback.
          </p>
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="primary"
            on:click={() => void startSpotifyAuthorization()}
            disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
          >
            {$spotifyAuth.authorizing
              ? "Authorizing…"
              : $spotifyAuth.authorized
                ? "Reconnect Spotify"
                : "Connect Spotify"}
          </button>
        </div>
      </header>

      <div class="system-card-body google-auth-body">
        {#if $spotifyAuth.loading}
          <p class="status">Checking Spotify authorization…</p>
        {:else if $spotifyAuth.error}
          <p class="status error">{$spotifyAuth.error}</p>
          <div class="google-auth-actions">
            <button
              type="button"
              class="ghost"
              on:click={refreshSpotifyAuth}
              disabled={$spotifyAuth.loading || $spotifyAuth.authorizing}
            >
              Try again
            </button>
          </div>
        {:else if $spotifyAuth.authorized}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$spotifyAuth.userEmail}</span
            >.
          </p>
          <p class="status muted">Access will refresh automatically.</p>
        {:else}
          <p class="status">Spotify is not connected.</p>
        {/if}

        <p class="status muted">
          Click "Connect Spotify" to authorize music control and playback
          features.
        </p>
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>Monarch Money</h3>
          <p class="system-card-caption">Connect your Monarch Money account.</p>
        </div>
      </header>

      <div class="system-card-body">
        {#if $monarchAuth.loading}
          <p class="status">Checking Monarch status…</p>
        {:else if $monarchAuth.configured}
          <p class="status success">
            Connected as <span class="google-auth-email"
              >{$monarchAuth.email}</span
            >.
          </p>
          <div class="system-card-actions">
            <button
              type="button"
              class="ghost"
              on:click={() => monarchAuth.remove()}
              disabled={$monarchAuth.saving}
            >
              Disconnect
            </button>
          </div>
        {:else}
          <div class="monarch-form">
            <label>
              Email
              <input
                type="email"
                bind:value={monarchEmail}
                placeholder="email@example.com"
              />
            </label>
            <label>
              Password
              <div class="password-input-wrapper">
                <input
                  type={showMonarchPassword ? "text" : "password"}
                  bind:value={monarchPassword}
                  placeholder="Password"
                />
                <button
                  type="button"
                  class="ghost icon-only"
                  on:click={() => (showMonarchPassword = !showMonarchPassword)}
                  title={showMonarchPassword
                    ? "Hide password"
                    : "Show password"}
                >
                  {#if showMonarchPassword}
                    <!-- Eye Off Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path
                        d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
                      ></path>
                      <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                  {:else}
                    <!-- Eye Icon -->
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"
                      ></path>
                      <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                  {/if}
                </button>
              </div>
            </label>
            <label>
              MFA Secret (Optional)
              <input
                type="text"
                bind:value={monarchMfaSecret}
                placeholder="MFA Secret"
              />
            </label>
            <p
              class="status muted"
              style="margin-top: -0.5rem; margin-bottom: 1rem; font-size: 0.8em;"
            >
              If you already use an app, you must <strong>reset MFA</strong> in Monarch
              Settings to see the secret key again. Enter the new key here AND in
              your app.
            </p>
            <button
              type="button"
              class="primary"
              on:click={saveMonarch}
              disabled={$monarchAuth.saving ||
                !monarchEmail ||
                !monarchPassword}
            >
              {$monarchAuth.saving ? "Saving..." : "Connect"}
            </button>
            {#if $monarchAuth.error}
              <p class="status error">{$monarchAuth.error}</p>
            {/if}
          </div>
        {/if}
      </div>
    </article>

    <article class="system-card">
      <header class="system-card-header">
        <div>
          <h3>MCP servers</h3>
          {#if $mcpServers.updatedAt}
            <p class="system-card-caption">
              Last updated {formatUpdatedAt($mcpServers.updatedAt) ?? ""}
            </p>
          {:else}
            <p class="system-card-caption">
              Toggle integrations available to the assistant.
            </p>
          {/if}
        </div>
        <div class="system-card-actions">
          <button
            type="button"
            class="ghost"
            on:click={refreshServers}
            disabled={$mcpServers.refreshing ||
              $mcpServers.saving ||
              $mcpServers.dirty}
          >
            {$mcpServers.refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      <div class="system-card-body">
        {#if $mcpServers.loading}
          <p class="status">Loading MCP servers…</p>
        {:else if $mcpServers.error}
          <p class="status error">{$mcpServers.error}</p>
        {:else}
          {#if !$mcpServers.servers.length}
            <p class="status">No MCP servers configured.</p>
          {:else}
            <ul class="server-list">
              {#each $mcpServers.servers as server}
                <li
                  class="server-row"
                  data-connected={server.connected}
                  data-pending={$mcpServers.pending[server.id]
                    ? "true"
                    : "false"}
                  data-dirty={$mcpServers.pendingChanges[server.id]
                    ? "true"
                    : "false"}
                >
                  <div class="server-row-header">
                    <div class="server-heading">
                      <h4>{server.id}</h4>
                      <div class="server-meta">
                        <span
                          class:connected={server.connected}
                          class:offline={!server.connected}
                        >
                          {server.connected ? "Connected" : "Offline"}
                        </span>
                        {#if server.module}
                          <span aria-hidden="true">•</span>
                          <span title={server.module}
                            >Module: {server.module}</span
                          >
                        {:else if server.command?.length}
                          <span aria-hidden="true">•</span>
                          <span title={server.command.join(" ")}
                            >Command: {server.command.join(" ")}</span
                          >
                        {/if}
                      </div>
                    </div>
                    <label class="toggle">
                      <input
                        type="checkbox"
                        checked={server.enabled}
                        disabled={$mcpServers.pending[server.id] ||
                          $mcpServers.saving}
                        on:change={(event) =>
                          toggleServer(
                            server.id,
                            (event.target as HTMLInputElement).checked,
                          )}
                      />
                      <span>{server.enabled ? "Enabled" : "Disabled"}</span>
                    </label>
                  </div>

                  <div class="server-row-body">
                    {#if server.id === "shell-control"}
                      <div class="shell-server-settings">
                        <div class="shell-setting">
                          <div class="shell-setting__info">
                            <span class="field-label">Require approval</span>
                            <span class="field-hint">
                              Commands only run when confirm=True if approval is required.
                            </span>
                          </div>
                          <label class="toggle">
                            <input
                              type="checkbox"
                              checked={isShellApprovalEnabled(server.env)}
                              disabled={$mcpServers.pending[server.id] ||
                                $mcpServers.saving}
                              on:change={(event) =>
                                handleShellEnv(
                                  server.id,
                                  "REQUIRE_APPROVAL",
                                  (event.target as HTMLInputElement).checked ? "true" : "false",
                                )}
                            />
                            <span>
                              {isShellApprovalEnabled(server.env)
                                ? "Approval required"
                                : "Yolo mode"}
                            </span>
                          </label>
                        </div>

                        <div class="shell-setting">
                          <div class="shell-setting__info">
                            <span class="field-label">Host profile</span>
                            <span class="field-hint">
                              Passed as HOST_PROFILE_ID; identifies this machine's profile.
                            </span>
                          </div>
                          <input
                            type="text"
                            value={server.env?.HOST_PROFILE_ID ?? ""}
                            autocomplete="off"
                            placeholder="e.g. xps13 or ryzen-desktop"
                            disabled={$mcpServers.pending[server.id] ||
                              $mcpServers.saving}
                            on:input={(event) =>
                              handleShellEnv(
                                server.id,
                                "HOST_PROFILE_ID",
                                (event.target as HTMLInputElement).value,
                              )}
                          />
                        </div>

                        <div class="shell-setting">
                          <div class="shell-setting__info">
                            <span class="field-label">Host root path</span>
                            <span class="field-hint">
                              Optional; override where host profiles are stored (e.g. GDrive sync folder).
                            </span>
                          </div>
                          <input
                            type="text"
                            value={server.env?.HOST_ROOT_PATH ?? ""}
                            autocomplete="off"
                            placeholder="e.g. /home/user/gdrive/host_profiles"
                            disabled={$mcpServers.pending[server.id] ||
                              $mcpServers.saving}
                            on:input={(event) =>
                              handleShellEnv(
                                server.id,
                                "HOST_ROOT_PATH",
                                (event.target as HTMLInputElement).value,
                              )}
                          />
                        </div>

                        <div class="shell-setting">
                          <div class="shell-setting__info">
                            <span class="field-label">Sudo password</span>
                            <span class="field-hint">
                              Optional; sent to sudo via stdin when commands start with sudo.
                            </span>
                          </div>
                          <div class="password-input-wrapper">
                            <input
                              type={showShellPassword ? "text" : "password"}
                              value={server.env?.SUDO_PASSWORD ?? ""}
                              autocomplete="off"
                              placeholder="Enter password"
                              disabled={$mcpServers.pending[server.id] ||
                                $mcpServers.saving}
                              on:input={(event) =>
                                handleShellEnv(
                                  server.id,
                                  "SUDO_PASSWORD",
                                  (event.target as HTMLInputElement).value,
                                )}
                            />
                            <button
                              type="button"
                              aria-label={showShellPassword ? "Hide password" : "Show password"}
                              disabled={$mcpServers.pending[server.id] ||
                                $mcpServers.saving}
                              on:click={() => (showShellPassword = !showShellPassword)}
                            >
                              {showShellPassword ? "Hide" : "Show"}
                            </button>
                          </div>
                        </div>
                      </div>
                    {/if}

                    <button
                      type="button"
                      class="tools-toggle"
                      class:open={expandedServers.has(server.id)}
                      on:click={() => toggleServerTools(server.id)}
                      aria-expanded={expandedServers.has(server.id)}
                      aria-controls="tools-{server.id}"
                    >
                      <span class="tools-toggle__label">
                        {server.tool_count} tool{server.tool_count === 1
                          ? ""
                          : "s"} available
                      </span>
                      <svg
                        class="tools-toggle__icon"
                        width="12"
                        height="12"
                        viewBox="0 0 12 12"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-hidden="true"
                      >
                        <path
                          d="M2.5 4.5L6 8L9.5 4.5"
                          stroke="currentColor"
                          stroke-width="1.5"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </button>

                    {#if expandedServers.has(server.id)}
                      <div id="tools-{server.id}" class="tools-dropdown">
                        {#if server.tools.length}
                          <ul class="tool-list">
                            {#each server.tools as tool}
                              <li
                                class="tool-row"
                                data-disabled={!tool.enabled}
                              >
                                <div class="tool-info">
                                  <span class="tool-name">{tool.name}</span>
                                  <span class="tool-qualified"
                                    >{tool.qualified_name}</span
                                  >
                                </div>
                                <label class="toggle">
                                  <input
                                    type="checkbox"
                                    checked={tool.enabled}
                                    disabled={!server.enabled ||
                                      $mcpServers.pending[server.id] ||
                                      $mcpServers.saving}
                                    on:change={(event) =>
                                      toggleTool(
                                        server.id,
                                        tool.name,
                                        (event.target as HTMLInputElement)
                                          .checked,
                                      )}
                                  />
                                  <span
                                    >{tool.enabled
                                      ? "Enabled"
                                      : "Disabled"}</span
                                  >
                                </label>
                              </li>
                            {/each}
                          </ul>
                        {:else}
                          <p class="status">Tool list unavailable.</p>
                        {/if}

                        {#if server.disabled_tools.length}
                          <p class="status warning">
                            Disabled tool ids: {server.disabled_tools.join(
                              ", ",
                            )}
                          </p>
                        {/if}
                      </div>
                    {/if}
                  </div>
                </li>
              {/each}
            </ul>
          {/if}
          {#if $mcpServers.saveError}
            <p class="status error">{$mcpServers.saveError}</p>
          {/if}
          {#if $mcpServers.dirty}
            <p class="status warning">
              Pending changes save when you close this modal.
            </p>
          {/if}
        {/if}
      </div>
    </article>

    <footer slot="footer" class="model-settings-footer system-settings-footer">
      {#if $mcpServers.saveError || $systemPrompt.saveError}
        <p class="status error">Resolve the errors above before closing.</p>
      {:else if $systemPrompt.saving || $mcpServers.saving}
        <p class="status">Saving changes…</p>
      {:else if $systemPrompt.dirty || $mcpServers.dirty}
        <p class="status">Pending changes; closing this modal will save.</p>
      {:else}
        <p class="status">Changes save when you close this modal.</p>
      {/if}
    </footer>
  </ModelSettingsDialog>
{/if}
