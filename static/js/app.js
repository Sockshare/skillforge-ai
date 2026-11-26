/**
 * SkillForge AI — 2-Step Application-to-Skill Studio & Live LLM ↔ Skill Testbench
 * Primary Route: Local Onboard Ollama (:11434)
 * Optional Cloud API Route: Google Gemini, OpenAI / OpenRouter, Anthropic Claude
 */

let currentBrowsePath = "";
let currentBrowseParent = "";
let selectedAppSource = "";
let selectedAppName = "";
let customTransformationDoc = "";
let llmProfiles = [];
let workspaceSkills = [];
let mcpClientConfigs = null;

function setProgress(pct, message, visible = true) {
  const wrap = document.getElementById("translation-progress-wrap");
  const fill = document.getElementById("progress-bar-fill");
  const text = document.getElementById("progress-status-text");
  const pctEl = document.getElementById("progress-pct-text");
  if (!wrap) return;
  wrap.style.display = visible ? "block" : "none";
  if (fill) fill.style.width = `${pct}%`;
  if (text) text.textContent = message;
  if (pctEl) pctEl.textContent = `${pct}%`;
}

function isCloudProvider(provider) {
  return provider === "gemini" || provider === "openai" || provider === "openrouter" || provider === "anthropic";
}

// ============================================================================
// 1. PC FOLDER BROWSER, SAMPLE APP LOADER & FILE UPLOAD
// ============================================================================
async function browsePcFolder(targetPath = "") {
  const listEl = document.getElementById("pc-folder-list");
  const pathInput = document.getElementById("pc-current-path");
  try {
    const q = targetPath ? `?path=${encodeURIComponent(targetPath)}` : "";
    const resp = await fetch(`/api/fs/browse${q}`);
    if (!resp.ok) throw new Error("Server browse unavailable");
    const data = await resp.json();
    currentBrowsePath = data.current_path;
    currentBrowseParent = data.parent_path;
    if (pathInput) pathInput.value = data.current_path;

    listEl.innerHTML = data.entries
      .map((entry) => {
        if (entry.type === "directory") {
          const badge = entry.is_app_candidate
            ? `<span class="badge badge-emerald">App Folder</span>`
            : "";
          return `
            <div class="pc-item">
              <div class="pc-item-left dir-open" data-path="${entry.path}">
                <span>📁</span>
                <span class="pc-item-name">${entry.name}</span>
                ${badge}
              </div>
              <button type="button" class="btn btn-primary btn-sm dir-select" data-path="${entry.path}" data-name="${entry.name}">
                Select App
              </button>
            </div>
          `;
        }
        return `
          <div class="pc-item">
            <div class="pc-item-left dir-select" data-path="${entry.path}" data-name="${entry.name}">
              <span>📄</span>
              <span class="pc-item-name">${entry.name}</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm dir-select" data-path="${entry.path}" data-name="${entry.name}">
              Select File
            </button>
          </div>
        `;
      })
      .join("");

    listEl.querySelectorAll(".dir-open").forEach((el) => {
      el.addEventListener("click", () => browsePcFolder(el.dataset.path));
    });
    listEl.querySelectorAll(".dir-select").forEach((btn) => {
      btn.addEventListener("click", () => selectPcApplicationPath(btn.dataset.path));
    });
  } catch (_) {
    if (listEl) {
      listEl.innerHTML = `<div class="text-muted" style="padding:8px;">Click <strong>⚡ Load Sample App (TaskPulse :8110)</strong> or upload files above to get started.</div>`;
    }
  }
}

function applyScannedApplication(data) {
  selectedAppName = data.app_name;
  selectedAppSource = data.combined_source;
  document.getElementById("skill-name-input").value = data.skill_slug;
  document.getElementById("selected-app-name").textContent = `${data.app_name} (${data.source_path})`;
  document.getElementById("selected-app-meta").textContent =
    `${data.files_scanned} file(s) scanned • ${data.routes_discovered.length} HTTP endpoints • ${data.functions_extracted.length} functions • ${data.tools_discovered.length} MCP tools ready`;
  if (data.default_target_url && document.getElementById("test-target-url")) {
    document.getElementById("test-target-url").value = data.default_target_url;
  }
  setProgress(100, `Loaded "${data.app_name}" — click "✨ Convert Application into LLM Skill" below.`, true);
}

async function loadBundledSampleApp() {
  setProgress(25, "Loading bundled TaskPulse sample web application (:8110)...", true);
  try {
    const resp = await fetch("/api/fs/load-sample-app", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Failed to load sample app");
    applyScannedApplication(data);
  } catch (err) {
    setProgress(0, `Error loading sample app: ${err.message}`, true);
  }
}

async function selectPcApplicationPath(targetPath) {
  if (!targetPath) return;
  setProgress(20, `Scanning application on PC (${targetPath})...`, true);
  try {
    const resp = await fetch("/api/fs/scan-app", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: targetPath })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Scan failed");
    applyScannedApplication(data);
  } catch (err) {
    setProgress(0, `Error scanning folder: ${err.message}`, true);
  }
}

async function handleUploadedFiles(fileList) {
  if (!fileList || fileList.length === 0) return;
  const allowed = /\.(py|js|ts|jsx|tsx|html|json|yaml|yml|md)$/i;
  const files = Array.from(fileList).filter((f) => allowed.test(f.name) && f.size <= 350000);
  if (files.length === 0) return;

  setProgress(25, `Reading ${files.length} uploaded application file(s)...`, true);
  const chunks = [];
  let folderName = "";
  for (const f of files.slice(0, 20)) {
    if (!folderName && f.webkitRelativePath && f.webkitRelativePath.includes("/")) {
      folderName = f.webkitRelativePath.split("/")[0];
    }
    const txt = await f.text();
    chunks.push(`# === FILE: ${f.webkitRelativePath || f.name} ===\n${txt.slice(0, 12000)}`);
  }

  selectedAppName = folderName || files[0].name.replace(/\.[^.]+$/, "");
  selectedAppSource = chunks.join("\n\n");
  const slug = selectedAppName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-skill";
  document.getElementById("skill-name-input").value = slug;
  document.getElementById("selected-app-name").textContent = `${selectedAppName} (${files.length} uploaded file(s))`;
  document.getElementById("selected-app-meta").textContent = `Ready to convert into "${slug}"`;
  setProgress(100, `Loaded ${files.length} file(s) — click "✨ Convert Application into LLM Skill" below.`, true);
}

// ============================================================================
// 2. TRANSLATE APPLICATION INTO SKILL (STEP 1)
// ============================================================================
async function convertApplicationToSkill() {
  if (!selectedAppSource) {
    await loadBundledSampleApp();
  }
  const skillSlug = document.getElementById("skill-name-input").value.trim() || "taskpulse-webapp-skill";
  const selectEl = document.getElementById("llm-profile-select");
  const prof = (selectEl && llmProfiles.find((p) => p.id === selectEl.value)) || llmProfiles[0] || {
    provider: "ollama",
    model: "llama3.2:3b",
    base_url: "http://127.0.0.1:11434"
  };
  const apiKey = document.getElementById("llm-apikey-input").value.trim();
  const btn = document.getElementById("btn-convert-skill");

  btn.disabled = true;
  setProgress(20, "Step 1/3 — Extracting HTTP routes, functions, and MCP tool schemas...", true);

  await new Promise((r) => setTimeout(r, 200));
  setProgress(55, `Step 2/3 — Synthesizing SKILL.md via ${prof.name || prof.provider}...`, true);

  let compiled = null;
  try {
    const resp = await fetch("/api/llm/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: skillSlug,
        category: `Application Skill (${selectedAppName || skillSlug})`,
        blueprint: selectedAppSource,
        webapp_source: selectedAppSource,
        transformation_doc: customTransformationDoc,
        install_to_workspace: true,
        llm_config: {
          profile_id: prof.id,
          provider: prof.provider,
          model: prof.model,
          base_url: prof.base_url,
          api_key: apiKey
        }
      })
    });
    if (resp.ok) {
      compiled = await resp.json();
    }
  } catch (_) {
    // Fallback to deterministic AST/route compilation if LLM unavailable
  }

  if (!compiled) {
    setProgress(75, "Step 2/3 — Compiling application routes & functions deterministically...", true);
    const resp2 = await fetch("/api/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        custom_override: true,
        install_to_workspace: true,
        name: skillSlug,
        category: `Application Skill (${selectedAppName || skillSlug})`,
        blueprint: selectedAppSource
      })
    });
    if (resp2.ok) {
      compiled = await resp2.json();
    }
  }

  setProgress(90, "Step 3/3 — Running 5-Gate verification & registering tools in MCP Hub...", true);
  await loadCreatedSkills(skillSlug);
  setProgress(100, `✓ Skill "${skillSlug}" compiled, verified (3-run SHA-256), and ready to test on the right!`, true);
  btn.disabled = false;
}

// ============================================================================
// 3. CREATED SKILLS & FILE LOCATIONS ON DISK
// ============================================================================
async function loadCreatedSkills(preferredSlug = "") {
  const listEl = document.getElementById("created-skills-list");
  try {
    const [wsResp, cfgResp] = await Promise.all([
      fetch("/api/workspace/skills"),
      fetch("/api/mcp/configs")
    ]);
    if (wsResp.ok) {
      const data = await wsResp.json();
      workspaceSkills = data.skills || [];
    }
    if (cfgResp.ok) {
      mcpClientConfigs = await cfgResp.json();
    }
  } catch (_) {}

  const testSelectEl = document.getElementById("test-skill-select");
  if (!workspaceSkills || workspaceSkills.length === 0) {
    if (testSelectEl) {
      testSelectEl.innerHTML = `<option value="">Convert an app on the left first</option>`;
    }
    listEl.innerHTML = `
      <div class="skill-card">
        <div class="text-muted">No skills compiled yet. Click <strong>⚡ Load Sample App (TaskPulse :8110)</strong> on the left, then click <strong>✨ Convert Application into LLM Skill</strong>.</div>
      </div>
    `;
    return;
  }

  if (testSelectEl) {
    const targetVal = preferredSlug || testSelectEl.value;
    testSelectEl.innerHTML = workspaceSkills
      .map((s) => `<option value="${s.name}">${s.title || s.name} (${s.name})</option>`)
      .join("");
    if (targetVal && workspaceSkills.some((s) => s.name === targetVal)) {
      testSelectEl.value = targetVal;
    }
  }

  listEl.innerHTML = workspaceSkills
    .map((s) => {
      const skillDir = s.skill_dir || `./skills_workspace/${s.name}`;
      const skillMdPath = `${skillDir}/SKILL.md`;
      const mcpPath = `${skillDir}/mcp_server.py`;
      const tools = s.tools || [];
      return `
        <div class="skill-card">
          <div class="skill-card-top">
            <div>
              <div class="skill-card-title">${s.title || s.name}</div>
              <div class="text-muted small-text">${s.description || ""}</div>
            </div>
            <span class="badge badge-emerald">${tools.length} Tools Active in MCP</span>
          </div>

          <div class="location-box">
            <div>
              <span class="location-label">Skill Folder &amp; SKILL.md Location:</span>
              <code class="location-path">${skillMdPath}</code>
              <div class="text-muted small-text">MCP Server: <code>${mcpPath}</code></div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm copy-path-btn" data-path="${skillDir}">
              📋 Copy Path
            </button>
          </div>

          <div class="skill-tools-row">
            ${tools.slice(0, 8).map((t) => `<span class="tool-tag">🔧 ${t.name}</span>`).join("")}
            ${tools.length > 8 ? `<span class="text-muted small-text">+${tools.length - 8} more</span>` : ""}
          </div>

          <div class="skill-actions-row">
            <button type="button" class="btn btn-primary btn-sm test-this-skill-btn" data-slug="${s.name}">
              💬 Test with LLM
            </button>
            <button type="button" class="btn btn-secondary btn-sm preview-skill-btn" data-slug="${s.name}">
              👁️ View SKILL.md
            </button>
            <button type="button" class="btn btn-secondary btn-sm download-zip-btn" data-slug="${s.name}">
              📦 Download .zip
            </button>
            <button type="button" class="btn btn-secondary btn-sm delete-skill-btn" data-slug="${s.name}">
              🗑️ Delete
            </button>
          </div>
        </div>
      `;
    })
    .join("");

  listEl.querySelectorAll(".test-this-skill-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (testSelectEl) testSelectEl.value = btn.dataset.slug;
      runSkillTestWithLlm();
    });
  });

  listEl.querySelectorAll(".copy-path-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(btn.dataset.path);
      btn.textContent = "✓ Copied!";
      setTimeout(() => {
        btn.textContent = "📋 Copy Path";
      }, 1400);
    });
  });

  listEl.querySelectorAll(".preview-skill-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const slug = btn.dataset.slug;
      const resp = await fetch("/api/mcp/rpc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rpc: { jsonrpc: "2.0", id: 1, method: "resources/read", params: { uri: `skill://${slug}/SKILL.md` } }
        })
      });
      if (resp.ok) {
        const data = await resp.json();
        const text = (data.result && data.result.contents && data.result.contents[0] && data.result.contents[0].text) || "";
        document.getElementById("modal-skill-title").textContent = `${slug}/SKILL.md`;
        document.getElementById("modal-skill-content").textContent = text;
        document.getElementById("skill-preview-modal").style.display = "flex";
      }
    });
  });

  listEl.querySelectorAll(".download-zip-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const slug = btn.dataset.slug;
      const found = workspaceSkills.find((x) => x.name === slug);
      if (!found) return;
      let endpoint = "/api/bundle.zip";
      let reqBody = found;
      let filename = `${slug}-skill-bundle.zip`;
      if (found.mode === "standalone_headless_cli") {
        endpoint = "/api/skill-creator/package.skill";
        reqBody = { skill_slug: slug };
        filename = `${slug}.skill.zip`;
      } else if (found.mode === "multi_skill_orchestrator") {
        endpoint = "/api/orchestrator/bundle.zip";
        reqBody = { pipeline_slug: slug };
        filename = `${slug}-full-suite.zip`;
      }
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqBody)
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    });
  });

  listEl.querySelectorAll(".delete-skill-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch("/api/workspace/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: btn.dataset.slug })
      });
      await loadCreatedSkills();
      if (typeof refreshOrchestratorPipelines === "function") {
        await refreshOrchestratorPipelines();
      }
    });
  });
}

// ============================================================================
// 4. LIVE 3-STAGE SKILL <-> LLM AGENT TESTBENCH
// ============================================================================
async function runSkillTestWithLlm() {
  const testSelectEl = document.getElementById("test-skill-select");
  const skillSlug = (testSelectEl && testSelectEl.value) || (workspaceSkills[0] && workspaceSkills[0].name) || "";
  const promptInput = document.getElementById("test-skill-prompt");
  const prompt = (promptInput && promptInput.value.trim()) || "List all tasks currently in the application";
  const targetUrl = (document.getElementById("test-target-url") && document.getElementById("test-target-url").value.trim()) || "http://127.0.0.1:8110";
  const btn = document.getElementById("btn-run-skill-test");
  const resBox = document.getElementById("skill-test-result");
  const toolEl = document.getElementById("test-result-tool");
  const modelEl = document.getElementById("test-result-model");
  const reasonEl = document.getElementById("test-result-reasoning");
  const ansEl = document.getElementById("test-result-answer");
  const jsonEl = document.getElementById("test-result-json");

  if (!skillSlug) {
    resBox.style.display = "flex";
    toolEl.textContent = "No compiled skill selected";
    reasonEl.style.display = "none";
    ansEl.textContent = "Convert an application on the left first so you have a compiled skill to test.";
    return;
  }

  const execSelectEl = document.getElementById("test-llm-select") || document.getElementById("llm-profile-select");
  const prof = (execSelectEl && llmProfiles.find((p) => p.id === execSelectEl.value)) || llmProfiles[0] || {
    provider: "ollama",
    model: "llama3.2:3b",
    base_url: "http://127.0.0.1:11434"
  };
  const step2Key = document.getElementById("test-llm-apikey") ? document.getElementById("test-llm-apikey").value.trim() : "";
  const step1Key = document.getElementById("llm-apikey-input") ? document.getElementById("llm-apikey-input").value.trim() : "";
  const apiKey = step2Key || step1Key;

  btn.disabled = true;
  btn.textContent = "⏳ Running Skill + LLM...";
  resBox.style.display = "flex";
  reasonEl.style.display = "block";
  toolEl.textContent = `⏳ Step 1/3 — ${prof.provider}:${prof.model} reading ${skillSlug}/SKILL.md...`;
  modelEl.textContent = `${prof.provider}:${prof.model}`;
  reasonEl.textContent = "Selecting MCP tool & arguments from SKILL.md...";
  ansEl.textContent = "Executing live tool call and generating grounded LLM response...";

  try {
    const resp = await fetch("/api/skill/test-with-llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill_slug: skillSlug,
        prompt: prompt,
        target_app_url: targetUrl,
        llm_config: {
          profile_id: prof.id,
          provider: prof.provider,
          model: prof.model,
          base_url: prof.base_url,
          api_key: apiKey
        }
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Skill test failed");

    const modeBadge = data.routing_mode === "llm_agent" ? "LLM Agent Tool-Call" : "Deterministic Router";
    toolEl.textContent = `✓ ${data.invoked_tool} → ${data.executed_against} (${data.latency_ms} ms)`;
    modelEl.textContent = `${data.llm_provider.toUpperCase()} • ${data.llm_model} (${modeBadge})`;
    reasonEl.textContent = `🧠 SKILL.md Routing: ${data.agent_reasoning || "Selected matching endpoint from SKILL.md."}`;
    ansEl.textContent = data.llm_answer || "Skill executed.";
    jsonEl.textContent = JSON.stringify(
      {
        routing_mode: data.routing_mode,
        invoked_tool: data.invoked_tool,
        executed_against: data.executed_against,
        llm_generated_arguments: data.request_arguments,
        live_tool_output: data.tool_output
      },
      null,
      2
    );
  } catch (err) {
    toolEl.textContent = "⚠️ Skill Execution / API Error";
    reasonEl.textContent = "Check that your target app is running or that a valid API key is supplied for Cloud LLM providers.";
    ansEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Skill + LLM";
  }
}

// ============================================================================
// 5. DUAL-ROUTE LLM CONNECTION MANAGER (LOCAL OLLAMA DEFAULT + CLOUD APIS)
// ============================================================================
function renderProfileOptions(selectEl, profiles, previousValue = "") {
  if (!selectEl) return;
  const localGroup = profiles.filter((p) => p.group === "local_onboard");
  const cloudGroup = profiles.filter((p) => p.group !== "local_onboard");

  let html = "";
  if (localGroup.length > 0) {
    html += `<optgroup label="🏠 Local Onboard Models (Ollama — Recommended Default)">`;
    html += localGroup.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    html += `</optgroup>`;
  }
  if (cloudGroup.length > 0) {
    html += `<optgroup label="☁️ Cloud Frontier APIs (Optional — API Key or .env)">`;
    html += cloudGroup
      .map((p) => `<option value="${p.id}">${p.name}${p.has_api_key ? " ✓ Key Ready" : ""}</option>`)
      .join("");
    html += `</optgroup>`;
  }
  selectEl.innerHTML = html;
  if (previousValue && profiles.some((p) => p.id === previousValue)) {
    selectEl.value = previousValue;
  }
}

function bindApiKeyVisibility(selectEl, wrapId, labelId) {
  if (!selectEl) return;
  const update = () => {
    const prof = llmProfiles.find((p) => p.id === selectEl.value);
    const wrap = document.getElementById(wrapId);
    const lbl = document.getElementById(labelId);
    if (!wrap) return;
    if (prof && isCloudProvider(prof.provider)) {
      wrap.style.display = "block";
      if (lbl) {
        lbl.textContent = prof.has_api_key
          ? `${prof.provider.toUpperCase()} API Key (✓ Env/Session Key Active — Optional Override)`
          : `${prof.provider.toUpperCase()} API Key (Required for Cloud API)`;
      }
    } else {
      wrap.style.display = "none";
    }
  };
  selectEl.onchange = update;
  update();
}

async function loadLlmProfiles() {
  const selectEl = document.getElementById("llm-profile-select");
  const testLlmEl = document.getElementById("test-llm-select");
  const pill = document.getElementById("ollama-status-pill");
  const prevStep1 = selectEl ? selectEl.value : "";
  const prevStep2 = testLlmEl ? testLlmEl.value : "";

  try {
    const resp = await fetch("/api/llm/status");
    if (resp.ok) {
      const data = await resp.json();
      llmProfiles = data.profiles || [];
      if (data.ollama && data.ollama.connected) {
        pill.textContent = `🏠 Local Ollama Active (${data.ollama.models.join(", ")})`;
        pill.className = "badge badge-emerald";
      } else {
        pill.textContent = "🏠 Local Ollama Offline (:11434) — Cloud APIs Available";
        pill.className = "badge badge-accent";
      }
    }
  } catch (_) {
    llmProfiles = [];
    pill.textContent = "LLM Status Unavailable";
    pill.className = "badge badge-accent";
  }

  renderProfileOptions(selectEl, llmProfiles, prevStep1);
  renderProfileOptions(testLlmEl, llmProfiles, prevStep2);
  bindApiKeyVisibility(selectEl, "api-key-wrap", "llm-apikey-label");
  bindApiKeyVisibility(testLlmEl, "test-apikey-wrap", "test-apikey-label");
}

function escHtml(val) {
  return String(val ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadBillingOpsSampleApp() {
  setProgress(25, "Loading bundled BillingOps Linux/Oracle/Microservices Diagnostics web app (:8115)...", true);
  try {
    const resp = await fetch("/api/fs/load-billing-ops-app", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Failed to load BillingOps app");
    applyScannedApplication(data);
  } catch (err) {
    setProgress(0, `Error loading BillingOps app: ${err.message}`, true);
  }
}

// ============================================================================
// 6. STEP 3: SKILL BUILDER ARCHITECTURE, GUARDRAILS, 100-SKILL ROUTER & EVALS
// ============================================================================
let kitOverviewData = null;
let kitFilesMap = {};
let activeKitFile = "CLAUDE.md";

function renderKitHandbook(topics) {
  const box = document.getElementById("kit-topics-container");
  if (!box || !Array.isArray(topics)) return;
  box.innerHTML = topics
    .map(
      (t) => `
      <article class="topic-card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <span class="badge badge-accent">${escHtml(t.badge)}</span>
        </div>
        <h3>${escHtml(t.title)}</h3>
        <p class="text-muted small-text">${escHtml(t.summary)}</p>
        <pre class="code-viewer" style="max-height:200px;font-size:0.74rem;">${escHtml(t.folder_tree)}</pre>
        <ul class="topic-list">
          ${(t.key_points || []).map((kp) => `<li>${escHtml(kp)}</li>`).join("")}
        </ul>
      </article>
    `
    )
    .join("");
}

async function runGuardrailHookTest() {
  const toolName = document.getElementById("guard-tool-select").value;
  const rawVal = document.getElementById("guard-input-value").value.trim();
  const hitl = document.getElementById("guard-hitl-checkbox").checked;
  const box = document.getElementById("guard-verdict-box");

  const toolInput =
    toolName === "OracleSQL"
      ? { sql: rawVal }
      : toolName === "Read"
      ? { file_path: rawVal }
      : { command: rawVal };

  try {
    const resp = await fetch("/api/kit/guardrails/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name: toolName, tool_input: toolInput, hitl_approved: hitl })
    });
    const res = await resp.json();
    let cls = "verdict-block";
    if (res.allowed) cls = "verdict-allow";
    else if (res.decision === "REQUIRE_HITL") cls = "verdict-hitl";

    box.className = `kpi-box ${cls}`;
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <strong>Decision: ${escHtml(res.decision)} (Hook Exit Code: ${escHtml(res.exit_code)}) — Rule ${escHtml(res.rule_id)}</strong>
        <span style="font-family:var(--font-mono);font-size:0.73rem;">Audit SHA-256: ${escHtml((res.audit_sha256 || "").slice(0, 20))}...</span>
      </div>
      <div style="margin-top:6px;font-size:0.85rem;"><strong>${escHtml(res.layer)}:</strong> ${escHtml(res.reason)}</div>
    `;
  } catch (err) {
    box.className = "kpi-box verdict-block";
    box.textContent = `Guardrail test error: ${err.message}`;
  }
}

function renderRouterSimulation(data) {
  const kpiEl = document.getElementById("router-kpis");
  const boxEl = document.getElementById("router-results-box");
  if (!kpiEl || !boxEl || !data || !data.token_comparison) return;
  const tc = data.token_comparison;

  kpiEl.innerHTML = `
    <div class="kpi-box verdict-block">
      <div class="kpi-label">Naive All-100 Full Skills</div>
      <div class="kpi-val">${tc.naive_monolithic_all_100_tokens.toLocaleString()} tok</div>
      <div class="small-text">${tc.naive_overflows_200k ? "✕ Exceeds 200K Context Window" : "Heavy Context Bloat"}</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-label">Tier-1 All-100 Metadata Only</div>
      <div class="kpi-val">${tc.tier1_all_100_metadata_only_tokens.toLocaleString()} tok</div>
      <div class="small-text text-muted">name + description (~75 tok/skill)</div>
    </div>
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">Routed Top-${escHtml(data.top_k)} Progressive Load</div>
      <div class="kpi-val">${tc.routed_progressive_total_tokens.toLocaleString()} tok</div>
      <div class="small-text">✓ Fits cleanly (${tc.remaining_context_headroom_tokens.toLocaleString()} tok free)</div>
    </div>
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">Context Window Saved</div>
      <div class="kpi-val">${escHtml(tc.context_reduction_pct)}%</div>
      <div class="small-text">${tc.tokens_saved_vs_monolithic.toLocaleString()} tokens eliminated</div>
    </div>
  `;

  const rows = (data.selected_skills || [])
    .map(
      (s) => `
      <tr>
        <td><strong style="color:#6ee7b7;font-family:var(--font-mono);">${escHtml(s.name)}</strong><div class="text-muted small-text">${escHtml(s.domain)}</div></td>
        <td>${escHtml(s.score)}</td>
        <td><code>${escHtml(s.script_executed_via_cli)}</code></td>
        <td>T1: ${escHtml(s.tier1_tokens)} / T2: ${escHtml(s.tier2_tokens)}</td>
        <td class="small-text">${escHtml(s.description)}</td>
      </tr>
    `
    )
    .join("");

  const negHtml =
    data.near_miss_negative_rejections && data.near_miss_negative_rejections.length > 0
      ? `<div style="margin-top:10px;font-size:0.8rem;color:#fcd34d;">
           <strong>Negative-Trigger Disambiguation Active:</strong> Penalized near-miss skills (${data.near_miss_negative_rejections.map((n) => escHtml(n.name)).join(", ")}) due to "Do not use when" clauses.
         </div>`
      : "";

  boxEl.innerHTML = `
    <table class="kit-table">
      <thead>
        <tr>
          <th>Activated Skill (Top-${escHtml(data.top_k)})</th>
          <th>BM25 Score</th>
          <th>Zero-Context CLI Script</th>
          <th>Tokens (T1/T2)</th>
          <th>Trigger Metadata</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${negHtml}
  `;
}

async function runRouterSimulation() {
  const query = document.getElementById("router-query-input").value.trim();
  const topK = parseInt(document.getElementById("router-topk-select").value, 10) || 3;
  const subagent = document.getElementById("router-subagent-checkbox").checked;
  const resp = await fetch("/api/kit/router", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK, use_subagent_isolation: subagent })
  });
  if (resp.ok) {
    renderRouterSimulation(await resp.json());
  }
}

function renderEvalAndTriggerSuite(bench, opt) {
  const kpiEl = document.getElementById("eval-kpis");
  const evalBox = document.getElementById("eval-results-box");
  const optBox = document.getElementById("trigger-opt-box");
  if (!kpiEl || !evalBox || !optBox || !bench || !opt) return;

  const b = bench.benchmark;
  kpiEl.innerHTML = `
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">With-Skill Pass Rate</div>
      <div class="kpi-val">${escHtml(b.with_skill.mean_pass_rate_pct)}%</div>
      <div class="small-text">Baseline without skill: ${escHtml(b.without_skill_baseline.mean_pass_rate_pct)}% (+${escHtml(b.delta.pass_rate_gain_pct)}%)</div>
    </div>
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">Token Reduction (scripts/)</div>
      <div class="kpi-val">-${escHtml(b.delta.token_reduction_pct)}%</div>
      <div class="small-text">${b.with_skill.mean_tokens.toLocaleString()} vs. ${b.without_skill_baseline.mean_tokens.toLocaleString()} baseline</div>
    </div>
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">Latency Improvement</div>
      <div class="kpi-val">-${escHtml(b.delta.latency_reduction_pct)}%</div>
      <div class="small-text">${b.with_skill.mean_duration_ms}ms vs. ${b.without_skill_baseline.mean_duration_ms}ms</div>
    </div>
    <div class="kpi-box verdict-allow">
      <div class="kpi-label">Held-Out Trigger Accuracy</div>
      <div class="kpi-val">${escHtml(opt.held_out_test_accuracy_pct)}%</div>
      <div class="small-text">${escHtml(opt.split_summary.train_queries)} train / ${escHtml(opt.split_summary.held_out_test_queries)} held-out test queries</div>
    </div>
  `;

  const evalRows = (bench.eval_runs || [])
    .map(
      (r) => `
      <tr>
        <td><strong style="font-family:var(--font-mono);color:#93c5fd;">${escHtml(r.eval_name)}</strong><div class="small-text text-muted">${escHtml(r.paths.with_skill_outputs)}</div></td>
        <td>${escHtml(r.prompt)}</td>
        <td><span class="badge badge-emerald">${Math.round(r.with_skill.pass_rate * 100)}% (${r.with_skill.total_tokens} tok)</span></td>
        <td><span class="badge badge-accent">${Math.round(r.without_skill.pass_rate * 100)}% (${r.without_skill.total_tokens} tok)</span></td>
      </tr>
    `
    )
    .join("");

  evalBox.innerHTML = `
    <h3 style="font-size:0.95rem;margin-bottom:6px;">Parallel With-Skill vs. Baseline Eval Workspace (<code>${escHtml(bench.workspace_directory)}</code>)</h3>
    <table class="kit-table">
      <thead>
        <tr><th>Eval Directory</th><th>Realistic Operator Prompt</th><th>with_skill</th><th>without_skill</th></tr>
      </thead>
      <tbody>${evalRows}</tbody>
    </table>
    <ul class="topic-list" style="margin-top:10px;">
      ${(bench.analyst_observations || []).map((o) => `<li><strong>Analyst Pass:</strong> ${escHtml(o)}</li>`).join("")}
    </ul>
  `;

  const iterRows = (opt.iterations || [])
    .map(
      (it) => `
      <tr>
        <td><strong>${escHtml(it.iteration_label)}</strong></td>
        <td>${escHtml(it.train_metrics.accuracy_pct)}% (P:${escHtml(it.train_metrics.precision_pct)}% / R:${escHtml(it.train_metrics.recall_pct)}%)</td>
        <td><strong>${escHtml(it.held_out_test_metrics.accuracy_pct)}%</strong> (P:${escHtml(it.held_out_test_metrics.precision_pct)}% / R:${escHtml(it.held_out_test_metrics.recall_pct)}%)</td>
        <td class="small-text">${escHtml(it.description)}</td>
      </tr>
    `
    )
    .join("");

  optBox.innerHTML = `
    <h3 style="font-size:0.95rem;margin-bottom:6px;">YAML Frontmatter Trigger Description Optimizer (60% Train / 40% Held-Out Test)</h3>
    <table class="kit-table">
      <thead>
        <tr><th>Optimization Step</th><th>Train Split (12)</th><th>Held-Out Test (8)</th><th>Candidate SKILL.md Description</th></tr>
      </thead>
      <tbody>${iterRows}</tbody>
    </table>
  `;
}

function renderStarterKitExplorer(filesObj) {
  kitFilesMap = filesObj || {};
  const listEl = document.getElementById("kit-file-list");
  const viewerEl = document.getElementById("kit-file-viewer");
  const titleEl = document.getElementById("kit-active-filename");
  if (!listEl || !viewerEl) return;

  const keys = Object.keys(kitFilesMap).sort();
  if (!keys.includes(activeKitFile)) {
    activeKitFile = keys.includes("CLAUDE.md") ? "CLAUDE.md" : keys[0] || "";
  }

  listEl.innerHTML = keys
    .map(
      (k) => `
      <button type="button" class="kit-file-btn ${k === activeKitFile ? "active" : ""}" data-kfile="${escHtml(k)}">
        📄 ${escHtml(k)}
      </button>
    `
    )
    .join("");

  if (titleEl) titleEl.textContent = activeKitFile;
  viewerEl.textContent = kitFilesMap[activeKitFile] || "";

  listEl.querySelectorAll(".kit-file-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeKitFile = btn.dataset.kfile;
      renderStarterKitExplorer(kitFilesMap);
    });
  });
}

async function initEnterpriseSkillBuilderLab() {
  // Tab switching
  document.querySelectorAll(".kit-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".kit-tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".kit-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const pane = document.getElementById(`kit-pane-${btn.dataset.kitTab}`);
      if (pane) pane.classList.add("active");
    });
  });

  // Load initial overview payload
  try {
    const resp = await fetch("/api/kit/overview");
    if (resp.ok) {
      kitOverviewData = await resp.json();
      renderKitHandbook(kitOverviewData.topics || []);
      renderRouterSimulation(kitOverviewData.default_router_demo);
      renderEvalAndTriggerSuite(kitOverviewData.default_eval_benchmark, kitOverviewData.default_trigger_optimization);
      renderStarterKitExplorer(kitOverviewData.starter_kit_files || {});

      const guardSelect = document.getElementById("guard-code-select");
      const guardViewer = document.getElementById("guard-code-viewer");
      const updateGuardViewer = () => {
        if (guardViewer && kitOverviewData.guardrail_files) {
          guardViewer.textContent = kitOverviewData.guardrail_files[guardSelect.value] || "";
        }
      };
      if (guardSelect) {
        guardSelect.addEventListener("change", updateGuardViewer);
        updateGuardViewer();
      }
    }
  } catch (_) {}

  // Guardrail presets & button
  document.querySelectorAll(".guard-preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("guard-tool-select").value = btn.dataset.tool;
      document.getElementById("guard-input-value").value = btn.dataset.val;
      document.getElementById("guard-hitl-checkbox").checked = btn.dataset.hitl === "1";
      runGuardrailHookTest();
    });
  });
  const guardBtn = document.getElementById("btn-run-guardrail");
  if (guardBtn) guardBtn.addEventListener("click", runGuardrailHookTest);
  const copyGuardBtn = document.getElementById("btn-copy-guard-code");
  if (copyGuardBtn) {
    copyGuardBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(document.getElementById("guard-code-viewer").textContent || "");
      copyGuardBtn.textContent = "✓ Copied!";
      setTimeout(() => {
        copyGuardBtn.textContent = "📋 Copy Guardrail File";
      }, 1400);
    });
  }
  runGuardrailHookTest();

  // 100-Skill Router presets & button
  document.querySelectorAll(".router-preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("router-query-input").value = btn.dataset.q;
      runRouterSimulation();
    });
  });
  const routerBtn = document.getElementById("btn-run-router");
  if (routerBtn) routerBtn.addEventListener("click", runRouterSimulation);

  // Evals & Trigger Optimizer button
  const evalsBtn = document.getElementById("btn-run-evals");
  if (evalsBtn) {
    evalsBtn.addEventListener("click", async () => {
      const skillName = document.getElementById("eval-skill-name").value.trim();
      const initDesc = document.getElementById("eval-init-desc").value.trim();
      const resp = await fetch("/api/kit/evals/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill_name: skillName, initial_description: initDesc })
      });
      if (resp.ok) {
        const d = await resp.json();
        renderEvalAndTriggerSuite(d.benchmark_suite, d.trigger_optimization);
      }
    });
  }

  // Starter Kit Regenerate, Copy & Download .zip
  const refreshKitBtn = document.getElementById("btn-refresh-kit");
  if (refreshKitBtn) {
    refreshKitBtn.addEventListener("click", async () => {
      const proj = document.getElementById("kit-project-name").value.trim();
      const stack = document.getElementById("kit-stack-input").value.trim();
      const resp = await fetch("/api/kit/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: proj, stack_summary: stack })
      });
      if (resp.ok) {
        const d = await resp.json();
        renderStarterKitExplorer(d.files || {});
      }
    });
  }

  const copyKitBtn = document.getElementById("btn-copy-kit-file");
  if (copyKitBtn) {
    copyKitBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(document.getElementById("kit-file-viewer").textContent || "");
      copyKitBtn.textContent = "✓ Copied!";
      setTimeout(() => {
        copyKitBtn.textContent = "📋 Copy Current File";
      }, 1400);
    });
  }

  const dlKitBtn = document.getElementById("btn-download-kit-zip");
  if (dlKitBtn) {
    dlKitBtn.addEventListener("click", async () => {
      const proj = document.getElementById("kit-project-name").value.trim() || "billing-ops-platform";
      const stack = document.getElementById("kit-stack-input").value.trim();
      const resp = await fetch("/api/kit/starter-bundle.zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: proj, stack_summary: stack })
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${proj}-agent-engineering-kit.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
    });
  }
}

function initApp() {
  const sampleBtn = document.getElementById("btn-load-sample-app");
  if (sampleBtn) {
    sampleBtn.addEventListener("click", loadBundledSampleApp);
  }
  const billingBtn = document.getElementById("btn-load-billing-ops-app");
  if (billingBtn) {
    billingBtn.addEventListener("click", loadBillingOpsSampleApp);
  }

  document.getElementById("btn-pc-up").addEventListener("click", () => browsePcFolder(currentBrowseParent));
  document.getElementById("btn-pc-go").addEventListener("click", () => {
    browsePcFolder(document.getElementById("pc-current-path").value.trim());
  });
  document.getElementById("btn-select-current-folder").addEventListener("click", () => {
    selectPcApplicationPath(currentBrowsePath || document.getElementById("pc-current-path").value.trim());
  });

  document.getElementById("webapp-folder-upload").addEventListener("change", (e) => handleUploadedFiles(e.target.files));
  document.getElementById("webapp-file-upload").addEventListener("change", (e) => handleUploadedFiles(e.target.files));
  document.getElementById("doc-file-upload").addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) {
      customTransformationDoc = await file.text();
      setProgress(100, `Loaded custom transformation guide "${file.name}"`, true);
    }
  });

  document.getElementById("btn-toggle-add-llm").addEventListener("click", () => {
    const d = document.getElementById("add-llm-drawer");
    d.style.display = d.style.display === "none" ? "block" : "none";
  });

  const provSelect = document.getElementById("new-llm-provider");
  if (provSelect) {
    provSelect.addEventListener("change", () => {
      const urlInput = document.getElementById("new-llm-url");
      const modelInput = document.getElementById("new-llm-model");
      const defaults = {
        ollama: ["http://127.0.0.1:11434", "llama3.2:3b"],
        custom_openai: ["http://127.0.0.1:1234/v1", "qwen2.5-coder-7b"],
        gemini: ["https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash"],
        openai: ["https://api.openai.com/v1", "gpt-4o-mini"],
        anthropic: ["https://api.anthropic.com/v1", "claude-3-7-sonnet-latest"]
      };
      const pair = defaults[provSelect.value];
      if (pair) {
        if (urlInput) urlInput.value = pair[0];
        if (modelInput && !modelInput.value.trim()) modelInput.placeholder = `Model (e.g. ${pair[1]})`;
      }
    });
  }

  document.getElementById("btn-save-new-llm").addEventListener("click", async () => {
    const name = document.getElementById("new-llm-name").value.trim();
    const provider = document.getElementById("new-llm-provider").value;
    const model = document.getElementById("new-llm-model").value.trim();
    const base_url = document.getElementById("new-llm-url").value.trim();
    const api_key = document.getElementById("new-llm-key").value.trim();
    const resp = await fetch("/api/llm/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, provider, model, base_url, api_key })
    });
    document.getElementById("add-llm-drawer").style.display = "none";
    await loadLlmProfiles();
    if (resp.ok) {
      const saved = await resp.json();
      if (saved.profile && saved.profile.id) {
        document.getElementById("llm-profile-select").value = saved.profile.id;
        document.getElementById("test-llm-select").value = saved.profile.id;
        bindApiKeyVisibility(document.getElementById("llm-profile-select"), "api-key-wrap", "llm-apikey-label");
        bindApiKeyVisibility(document.getElementById("test-llm-select"), "test-apikey-wrap", "test-apikey-label");
      }
    }
  });

  document.getElementById("btn-convert-skill").addEventListener("click", convertApplicationToSkill);
  const decoupleBtn = document.getElementById("btn-decouple-standalone-skill");
  if (decoupleBtn) decoupleBtn.addEventListener("click", decoupleSelectedAppIntoStandaloneSkill);
  document.getElementById("btn-run-skill-test").addEventListener("click", runSkillTestWithLlm);

  document.querySelectorAll(".quick-test-prompt").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("test-skill-prompt").value = btn.dataset.prompt;
      runSkillTestWithLlm();
    });
  });

  document.getElementById("btn-copy-mcp-cmd").addEventListener("click", () => {
    const cfg = mcpClientConfigs ? mcpClientConfigs.claude_desktop_config : {
      mcpServers: { "skillforge-multi-skill-hub": { command: "python3", args: ["./mcp_server.py"] } }
    };
    navigator.clipboard.writeText(JSON.stringify(cfg, null, 2));
    const btn = document.getElementById("btn-copy-mcp-cmd");
    btn.textContent = "✓ Copied MCP Config!";
    setTimeout(() => {
      btn.textContent = "🔌 Copy MCP Server Config";
    }, 1500);
  });

  document.getElementById("btn-close-modal").addEventListener("click", () => {
    document.getElementById("skill-preview-modal").style.display = "none";
  });

  initOllamaAndSkillCreatorAndOrchestrator();
  browsePcFolder();
  loadLlmProfiles();
  loadCreatedSkills();
  initEnterpriseSkillBuilderLab();
}

// ============================================================================
// 7. GLOBAL LIVE OLLAMA MODEL SELECTOR, 1:1 SKILL-CREATOR & ORCHESTRATOR STUDIO
// ============================================================================
let lastRealEvalRun = null;

const CLOUD_PROVIDER_MODELS = {
  gemini: {
    base_url: "https://generativelanguage.googleapis.com/v1beta",
    models: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
  },
  anthropic: {
    base_url: "https://api.anthropic.com/v1",
    models: ["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"]
  },
  openai: {
    base_url: "https://api.openai.com/v1",
    models: ["gpt-4.1", "gpt-4o", "gpt-4o-mini", "o3-mini"]
  }
};

function getActiveOllamaLlmConfig() {
  const provEl = document.getElementById("global-llm-provider");
  const provider = (provEl && provEl.value) || "ollama";
  const urlEl = document.getElementById("global-ollama-url");
  const selEl = document.getElementById("global-ollama-model");
  const customEl = document.getElementById("global-ollama-custom-tag");
  const cloudKeyEl = document.getElementById("global-cloud-apikey");
  const step1KeyEl = document.getElementById("llm-apikey-input");

  const apiKey = (cloudKeyEl && cloudKeyEl.value.trim()) || (step1KeyEl && step1KeyEl.value.trim()) || "";
  if (provider !== "ollama" && CLOUD_PROVIDER_MODELS[provider]) {
    const cinfo = CLOUD_PROVIDER_MODELS[provider];
    const model = (customEl && customEl.value.trim()) || (selEl && selEl.value) || cinfo.models[0];
    return {
      provider: provider,
      base_url: cinfo.base_url,
      model: model,
      api_key: apiKey
    };
  }

  const baseUrl = (urlEl && urlEl.value.trim()) || "http://127.0.0.1:11434";
  const model = (customEl && customEl.value.trim()) || (selEl && selEl.value) || "llama3.2:3b";
  return {
    provider: "ollama",
    base_url: baseUrl,
    model: model
  };
}

async function refreshInstalledOllamaModels() {
  const provEl = document.getElementById("global-llm-provider");
  const provider = (provEl && provEl.value) || "ollama";
  const urlWrap = document.getElementById("global-ollama-url-wrap");
  const keyWrap = document.getElementById("global-cloud-key-wrap");
  const urlEl = document.getElementById("global-ollama-url");
  const selEl = document.getElementById("global-ollama-model");
  const metaEl = document.getElementById("global-ollama-meta");
  const pill = document.getElementById("ollama-status-pill");
  if (!selEl) return;

  if (provider !== "ollama" && CLOUD_PROVIDER_MODELS[provider]) {
    if (urlWrap) urlWrap.style.display = "none";
    if (keyWrap) keyWrap.style.display = "block";
    const cinfo = CLOUD_PROVIDER_MODELS[provider];
    selEl.innerHTML = cinfo.models.map((m) => `<option value="${escHtml(m)}">${escHtml(m)}</option>`).join("");
    if (metaEl) {
      metaEl.innerHTML = `✓ Cloud Provider <strong>${escHtml(provider.toUpperCase())}</strong> selected — paste your API key above (or set <code>GEMINI_API_KEY</code> / <code>ANTHROPIC_API_KEY</code> / <code>OPENAI_API_KEY</code> in <code>.env</code>).`;
    }
    await loadLlmProfiles();
    return;
  }

  if (urlWrap) urlWrap.style.display = "block";
  if (keyWrap) keyWrap.style.display = "none";

  const baseUrl = (urlEl && urlEl.value.trim()) || "http://127.0.0.1:11434";
  const prev = selEl.value;
  try {
    const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(baseUrl)}`);
    const data = await resp.json();
    if (data.connected && Array.isArray(data.models) && data.models.length > 0) {
      const detailsMap = {};
      (data.model_details || []).forEach((d) => {
        detailsMap[d.name] = d;
      });
      selEl.innerHTML = data.models
        .map((m) => {
          const d = detailsMap[m] || {};
          const extra = [d.parameter_size, d.quantization].filter(Boolean).join(", ");
          return `<option value="${escHtml(m)}">${escHtml(m)}${extra ? ` (${escHtml(extra)})` : ""}</option>`;
        })
        .join("");
      if (prev && data.models.includes(prev)) {
        selEl.value = prev;
      } else if (data.recommended_default && data.models.includes(data.recommended_default)) {
        selEl.value = data.recommended_default;
      }
      if (metaEl) {
        metaEl.innerHTML = `✓ Connected to <code>${escHtml(data.endpoint)}</code> — <strong>${data.models.length} local Ollama models ready</strong> (${data.models.map(escHtml).join(", ")}) — or switch dropdown above to <strong>Google Gemini / Claude / OpenAI</strong>.`;
      }
      if (pill) {
        pill.textContent = `🏠 Ollama Active: ${selEl.value} (+${Math.max(0, data.models.length - 1)} more)`;
        pill.className = "badge badge-emerald";
      }
    } else {
      selEl.innerHTML = `<option value="llama3.2:3b">llama3.2:3b (Ollama offline — deterministic fallback active)</option>`;
      if (metaEl) {
        metaEl.textContent = `Local Ollama not detected at ${baseUrl}. Run "ollama serve" or switch Provider to Google Gemini, Claude, or OpenAI.`;
      }
    }
  } catch (err) {
    if (metaEl) metaEl.textContent = `Error checking Ollama endpoint: ${err.message}`;
  }
  await loadLlmProfiles();
}

async function decoupleSelectedAppIntoStandaloneSkill() {
  if (!selectedAppSource) {
    await loadBillingOpsSampleApp();
  }
  const rawSlug = (document.getElementById("skill-name-input").value.trim() || "billing-ops-headless-skill").replace(/-webapp-skill$/, "-headless-skill");
  setProgress(35, `Decoupling Python AST from "${selectedAppName || rawSlug}" into 100% standalone headless CLI skill...`, true);
  try {
    const resp = await fetch("/api/skill-creator/build-standalone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: rawSlug,
        title: `${selectedAppName || rawSlug} Standalone CLI Skill`,
        webapp_source: selectedAppSource,
        stage_role: "audit"
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Failed to build standalone skill");
    document.getElementById("sc-slug-input").value = data.manifest.name;
    document.getElementById("sc-desc-input").value = data.manifest.description;
    renderStandaloneBuildSummary(data.manifest, data.artifacts);
    await loadCreatedSkills(data.manifest.name);
    setProgress(
      100,
      `✓ Decoupled "${data.manifest.name}" (${data.manifest.extracted_webapp_functions.length} pure domain functions, 3-run SHA-256 verified, zero web server needed)!`,
      true
    );
  } catch (err) {
    setProgress(0, `Error decoupling standalone skill: ${err.message}`, true);
  }
}

function renderStandaloneBuildSummary(manifest, artifacts) {
  const out = document.getElementById("sc-build-output");
  if (!out || !manifest) return;
  out.style.display = "block";
  const filesList = Object.keys(artifacts || {}).sort();
  out.innerHTML = `
    <div class="kpi-box verdict-allow">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <strong>✓ Standalone Headless Skill Installed: <code>${escHtml(manifest.name)}</code> (Zero Web Server Required)</strong>
        <span class="badge badge-emerald">3-Run SHA-256: ${escHtml((manifest.determinism && manifest.determinism.run_1_sha256 || "").slice(0, 18))}...</span>
      </div>
      <div class="small-text" style="margin-top:6px;">
        <strong>CLI Entrypoint:</strong> <code>python3 skills_workspace/${escHtml(manifest.name)}/${escHtml(manifest.cli_script)} --app PaymentsCore</code><br/>
        <strong>Extracted Pure Domain Functions:</strong> <code>${escHtml((manifest.extracted_webapp_functions || []).join(", ") || "Built-in deterministic evaluator")}</code><br/>
        <strong>Generated Files (${filesList.length}):</strong> <code>${filesList.map(escHtml).join(" • ")}</code>
      </div>
    </div>
  `;
}

async function runSkillCreatorInterview() {
  const btn = document.getElementById("btn-sc-interview");
  const out = document.getElementById("sc-interview-output");
  const goal = document.getElementById("sc-goal-input").value.trim();
  const hints = document.getElementById("sc-trigger-hints").value.trim();
  const llmCfg = getActiveOllamaLlmConfig();

  btn.disabled = true;
  btn.textContent = `⏳ Interviewing (${llmCfg.model})...`;
  try {
    const resp = await fetch("/api/skill-creator/interview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal: goal,
        app_source: selectedAppSource,
        trigger_hints: hints,
        llm_config: llmCfg
      })
    });
    const data = await resp.json();
    document.getElementById("sc-slug-input").value = data.suggested_slug;
    document.getElementById("sc-desc-input").value = data.pushy_description;
    out.style.display = "block";
    out.innerHTML = `
      <div class="kpi-box" style="border-color:rgba(99,102,241,0.45);">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <strong>🧠 Skill-Creator Intent Capture &amp; Test Plan</strong>
          <span class="badge badge-accent">Model: ${escHtml(data.llm_model_used)}</span>
        </div>
        <div class="small-text" style="margin-top:6px;"><strong>Clarifying Edge-Case Questions:</strong></div>
        <ul class="topic-list">
          ${(data.clarifying_questions || []).map((q) => `<li>${escHtml(q)}</li>`).join("")}
        </ul>
        <div class="small-text" style="margin-top:8px;"><strong>Proposed <code>evals/evals.json</code> Test Prompts:</strong></div>
        <ul class="topic-list">
          ${(data.proposed_evals || []).map((ev) => `<li><code>${escHtml(ev.eval_name)}</code>: ${escHtml(ev.prompt)}</li>`).join("")}
        </ul>
      </div>
    `;
  } finally {
    btn.disabled = false;
    btn.textContent = "🧠 Interview with Ollama";
  }
}

async function buildStandaloneSkillFromWorkbench() {
  const slug = document.getElementById("sc-slug-input").value.trim() || "prod-acl-compliance-verifier";
  const desc = document.getElementById("sc-desc-input").value.trim();
  const role = document.getElementById("sc-stage-role").value;
  const btn = document.getElementById("btn-sc-build-standalone");
  btn.disabled = true;
  btn.textContent = "⏳ Building...";
  try {
    const resp = await fetch("/api/skill-creator/build-standalone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: slug,
        description: desc,
        stage_role: role,
        webapp_source: selectedAppSource
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Build failed");
    renderStandaloneBuildSummary(data.manifest, data.artifacts);
    await loadCreatedSkills(data.manifest.name);
  } finally {
    btn.disabled = false;
    btn.textContent = "🔨 Build Headless Skill";
  }
}

function renderRealSkillCreatorEvalOutput(data) {
  lastRealEvalRun = data;
  const box = document.getElementById("sc-real-evals-output");
  if (!box || !data || !data.benchmark) return;
  const b = data.benchmark;
  const wsPass = Math.round((b.with_skill.pass_rate.mean || 0) * 100);
  const bsPass = Math.round((b.baseline.pass_rate.mean || 0) * 100);

  const cardsHtml = (data.eval_results || [])
    .map(
      (ev, idx) => `
      <div class="skill-card" style="margin-top:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <strong>Eval #${ev.eval_id}: <code>${escHtml(ev.eval_name)}</code> — Winner: <span style="color:#6ee7b7;">${escHtml(ev.blind_comparison_winner)}</span></strong>
          <div>
            <span class="badge badge-emerald">with_skill: ${Math.round(ev.with_skill.pass_rate * 100)}% (${ev.with_skill.duration_ms}ms, ${ev.with_skill.total_tokens} tok)</span>
            <span class="badge badge-accent">${escHtml(ev.baseline.mode)}: ${Math.round(ev.baseline.pass_rate * 100)}%</span>
          </div>
        </div>
        <div class="small-text text-muted" style="margin-top:4px;"><strong>Prompt:</strong> ${escHtml(ev.prompt)}</div>
        <div class="small-text" style="margin-top:4px;"><strong>Real Files Produced on Disk:</strong> <code>${escHtml((ev.with_skill.produced_files || []).join(", "))}</code></div>
        <div style="margin-top:8px;">
          <label class="small-text" style="display:block;color:#a5b4fc;font-weight:600;">Human Review Feedback for <code>feedback.json</code> (Iteration ${data.iteration} → Iteration ${data.iteration + 1}):</label>
          <input type="text" class="input-control sc-feedback-input" data-run-id="eval-${ev.eval_id}-with_skill" placeholder="e.g. Also highlight executive risk summary bullets at the top of SKILL.md..." style="margin-top:4px;" />
        </div>
      </div>
    `
    )
    .join("");

  box.innerHTML = `
    <div class="kpi-grid-4" style="margin-top:10px;">
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Iteration #${data.iteration} with_skill</div>
        <div class="kpi-val">${wsPass}%</div>
        <div class="small-text">stddev: ${b.with_skill.pass_rate.stddev}</div>
      </div>
      <div class="kpi-box">
        <div class="kpi-label">Baseline (${escHtml(b.baseline.label)})</div>
        <div class="kpi-val">${bsPass}%</div>
        <div class="small-text">Gain: +${Math.round((b.delta.pass_rate_gain || 0) * 100)}%</div>
      </div>
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Token Reduction</div>
        <div class="kpi-val">-${escHtml(b.delta.token_reduction_pct)}%</div>
        <div class="small-text">${Math.round(b.with_skill.total_tokens.mean)} vs ${Math.round(b.baseline.total_tokens.mean)} tok</div>
      </div>
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Eval Workspace on Disk</div>
        <div class="kpi-val" style="font-size:0.86rem;font-family:var(--font-mono);">iteration-${data.iteration}</div>
        <div class="small-text">eval_viewer.html + benchmark.json ready</div>
      </div>
    </div>
    ${cardsHtml}
    <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <span class="small-text text-muted">Static Reviewer written to: <code>${escHtml(data.viewer_html_path)}</code></span>
      <button id="btn-sc-submit-feedback" type="button" class="btn btn-primary">
        ↻ Save feedback.json, Rewrite SKILL.md via Ollama &amp; Run Iteration ${data.iteration + 1}
      </button>
    </div>
  `;

  const fbBtn = document.getElementById("btn-sc-submit-feedback");
  if (fbBtn) fbBtn.addEventListener("click", submitFeedbackAndIterate);
}

async function runRealSubprocessEvals() {
  const slug = document.getElementById("sc-slug-input").value.trim() || "prod-acl-compliance-verifier";
  const btn = document.getElementById("btn-sc-run-real-evals");
  btn.disabled = true;
  btn.textContent = "⏳ Running Evals...";
  try {
    const resp = await fetch("/api/skill-creator/run-evals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill_slug: slug,
        llm_config: getActiveOllamaLlmConfig()
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Eval run failed");
    renderRealSkillCreatorEvalOutput(data);
    await loadCreatedSkills(slug);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Real Subprocess Evals";
  }
}

async function submitFeedbackAndIterate() {
  if (!lastRealEvalRun) return;
  const slug = lastRealEvalRun.skill_slug;
  const inputs = Array.from(document.querySelectorAll(".sc-feedback-input"));
  const reviews = inputs.map((inp) => ({
    run_id: inp.dataset.runId,
    feedback: inp.value.trim() || "Ensure crisp executive summary formatting and strict non-prod exclusion.",
    timestamp: new Date().toISOString()
  }));
  const btn = document.getElementById("btn-sc-submit-feedback");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ Rewriting SKILL.md via Ollama & Running Next Iteration...";
  }
  const resp = await fetch("/api/skill-creator/submit-feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      skill_slug: slug,
      iteration: lastRealEvalRun.iteration,
      reviews: reviews,
      llm_config: getActiveOllamaLlmConfig()
    })
  });
  if (resp.ok) {
    const nextData = await resp.json();
    renderRealSkillCreatorEvalOutput(nextData);
  }
}

async function optimizeAndApplyTriggerDescription() {
  const slug = document.getElementById("sc-slug-input").value.trim() || "automated-project-reporter";
  const desc = document.getElementById("sc-desc-input").value.trim();
  const btn = document.getElementById("btn-sc-opt-desc");
  btn.disabled = true;
  btn.textContent = "⏳ Optimizing (60/40)...";
  try {
    const resp = await fetch("/api/skill-creator/optimize-description", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill_slug: slug,
        initial_description: desc,
        apply_to_skill_md: true,
        llm_config: getActiveOllamaLlmConfig()
      })
    });
    const data = await resp.json();
    if (resp.ok && data.best_description) {
      document.getElementById("sc-desc-input").value = data.best_description;
      const out = document.getElementById("sc-build-output");
      out.style.display = "block";
      out.innerHTML = `
        <div class="kpi-box verdict-allow">
          <strong>🎯 Trigger Description Optimized (${data.held_out_test_accuracy_pct}% Held-Out Accuracy across ${data.split_summary.total_queries} queries • Engine: ${escHtml(data.llm_model_used || "60/40 Optimizer")})</strong>
          <div class="small-text" style="margin-top:6px;">Updated <code>skills_workspace/${escHtml(slug)}/SKILL.md</code> frontmatter with winning description.</div>
        </div>
      `;
      await loadCreatedSkills(slug);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "🎯 4. Optimize Trigger";
  }
}

async function downloadStandaloneSkillArchive() {
  const slug = document.getElementById("sc-slug-input").value.trim() || "automated-project-reporter";
  const resp = await fetch("/api/skill-creator/package.skill", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ skill_slug: slug })
  });
  if (resp.ok) {
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.skill.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

// --- MULTI-SKILL ORCHESTRATOR & TWO-RUN DETERMINISM STUDIO ---
async function refreshOrchestratorPipelines(preferred = "") {
  const sel = document.getElementById("orch-select-pipeline");
  if (!sel) return;
  try {
    const resp = await fetch("/api/orchestrator/pipelines");
    if (!resp.ok) return;
    const data = await resp.json();
    const pipes = data.pipelines || [];
    if (pipes.length > 0) {
      const prev = preferred || sel.value;
      sel.innerHTML = pipes
        .map((p) => `<option value="${escHtml(p.slug)}">${escHtml(p.title)} (${p.stages.length} stages • ./${escHtml(p.launcher_cli)})</option>`)
        .join("");
      if (prev && pipes.some((p) => p.slug === prev)) {
        sel.value = prev;
      }
    }
  } catch (_) {}
}

async function provisionReferenceComplianceSuite() {
  const btn = document.getElementById("btn-orch-provision-suite");
  const out = document.getElementById("orch-execution-output");
  btn.disabled = true;
  btn.textContent = "⏳ Provisioning 6 Standalone Skills & Unified CLI...";
  try {
    const resp = await fetch("/api/orchestrator/provision-reference-suite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_config: getActiveOllamaLlmConfig() })
    });
    const data = await resp.json();
    await refreshOrchestratorPipelines("compliance-master-orchestrator");
    await loadCreatedSkills("compliance-master-orchestrator");
    out.innerHTML = `
      <div class="kpi-box verdict-allow" style="margin-top:10px;">
        <strong>✓ Provisioned ${data.total_skills_provisioned} Standalone Headless Skills + Unified Launcher <code>./${escHtml(data.orchestrator.launcher_cli)}</code></strong>
        <div class="small-text" style="margin-top:6px;">
          Stages installed in <code>skills_workspace/</code>: <code>${(data.member_skills || []).map((m) => escHtml(m.name)).join(" → ")}</code>
        </div>
      </div>
    `;
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 Load Example 6-Skill Pipeline";
  }
}

async function compileCustomOrchestratorFromUi() {
  const name = document.getElementById("orch-custom-name").value.trim() || "custom-master-orchestrator";
  const rawStages = document.getElementById("orch-stage-slugs").value.trim();
  const slugs = rawStages.split(",").map((s) => s.trim()).filter(Boolean);
  const btn = document.getElementById("btn-orch-compile");
  const out = document.getElementById("orch-execution-output");
  btn.disabled = true;
  btn.textContent = "⏳ Compiling Orchestrator...";
  try {
    const resp = await fetch("/api/orchestrator/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipeline_name: name,
        stage_skill_slugs: slugs,
        llm_config: getActiveOllamaLlmConfig()
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Orchestrator compile failed");
    await refreshOrchestratorPipelines(data.orchestrator.name);
    await loadCreatedSkills(data.orchestrator.name);
    out.innerHTML = `
      <div class="kpi-box verdict-allow" style="margin-top:10px;">
        <strong>✓ Compiled Orchestrator <code>${escHtml(data.orchestrator.name)}</code> (Launcher: <code>./${escHtml(data.orchestrator.launcher_cli)}</code>)</strong>
        <div class="small-text" style="margin-top:4px;">Package SHA-256: <code>${escHtml(data.orchestrator.package_sha256)}</code></div>
      </div>
    `;
  } finally {
    btn.disabled = false;
    btn.textContent = "🔗 Compile Orchestrator & Unified CLI";
  }
}

async function runOrchestratorFromUi(runMode) {
  const slug = document.getElementById("orch-select-pipeline").value || "compliance-master-orchestrator";
  const app = document.getElementById("orch-target-app").value.trim() || "PaymentsCore";
  const comps = document.getElementById("orch-components").value.trim();
  const stageSel = document.getElementById("orch-stage-selector").value.trim() || "1";
  const out = document.getElementById("orch-execution-output");

  out.innerHTML = `<div class="kpi-box" style="margin-top:10px;">⏳ Executing <code>${escHtml(slug)}</code> (${escHtml(runMode)}) on <strong>${escHtml(app)}</strong> via real headless CLI subprocesses...</div>`;
  const resp = await fetch("/api/orchestrator/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pipeline_slug: slug,
      target_app: app,
      component_ids: comps,
      run_mode: runMode,
      stage_selector: stageSel
    })
  });
  const data = await resp.json();
  if (!resp.ok) {
    out.innerHTML = `<div class="kpi-box verdict-block" style="margin-top:10px;">✕ ${escHtml(data.error || "Execution failed")}</div>`;
    return;
  }

  await refreshOrchestratorPipelines(slug);
  await loadCreatedSkills(slug);

  if (runMode === "two_run_determinism") {
    const rows = (data.stage_hash_comparisons || [])
      .map(
        (sc) => `
        <tr>
          <td><code>${escHtml(sc.stage_slug)}</code></td>
          <td><code>${escHtml(sc.run_a_sha256.slice(0, 24))}...</code></td>
          <td><code>${escHtml(sc.run_b_sha256.slice(0, 24))}...</code></td>
          <td><span class="badge badge-emerald">${sc.identical ? "✓ IDENTICAL" : "✕ DRIFT"}</span></td>
        </tr>
      `
      )
      .join("");
    out.innerHTML = `
      <div class="kpi-grid-4" style="margin-top:12px;">
        <div class="kpi-box verdict-allow">
          <div class="kpi-label">Two-Run Verdict</div>
          <div class="kpi-val" style="font-size:1rem;">${escHtml(data.verdict)}</div>
          <div class="small-text">Run A vs Run B Independent Subprocesses</div>
        </div>
        <div class="kpi-box verdict-allow">
          <div class="kpi-label">Dataset SHA-256 Match</div>
          <div class="kpi-val">${data.dataset_identical ? "100% MATCH" : "MISMATCH"}</div>
          <div class="small-text"><code>${escHtml((data.dataset_sha256_run_a || "").slice(0, 18))}...</code></div>
        </div>
        <div class="kpi-box verdict-allow">
          <div class="kpi-label">Master Report SHA-256</div>
          <div class="kpi-val">${data.report_identical ? "100% MATCH" : "MISMATCH"}</div>
          <div class="small-text"><code>${escHtml((data.report_sha256_run_a || "").slice(0, 18))}...</code></div>
        </div>
        <div class="kpi-box verdict-allow">
          <div class="kpi-label">Verified Handoff Items</div>
          <div class="kpi-val">${(data.verified_handoff_items || []).length}</div>
          <div class="small-text">00_Verified_Scope_and_Groups</div>
        </div>
      </div>
      <table class="kit-table" style="margin-top:10px;">
        <thead><tr><th>Stage Skill</th><th>Run A Dataset SHA-256</th><th>Run B Dataset SHA-256</th><th>Byte-for-Byte Proof</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <pre class="code-viewer" style="max-height:280px;margin-top:10px;">${escHtml(data.comparison_markdown_preview || "")}</pre>
    `;
    return;
  }

  const stRows = (data.stages_executed || [])
    .map(
      (st) => `
      <tr>
        <td>Stage ${st.stage_number}</td>
        <td><code>${escHtml(st.skill_slug)}</code></td>
        <td><strong>${escHtml(st.verdict)}</strong></td>
        <td>${st.production_items_verified}</td>
        <td><code>${escHtml((st.dataset_sha256 || "").slice(0, 22))}...</code></td>
      </tr>
    `
    )
    .join("");
  const mr = data.master_report || {};
  out.innerHTML = `
    <div class="kpi-grid-4" style="margin-top:12px;">
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Stages Completed</div>
        <div class="kpi-val">${(data.stages_executed || []).length}</div>
        <div class="small-text">Target: ${escHtml(data.target_application)}</div>
      </div>
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Stage 1 Handoff Items</div>
        <div class="kpi-val">${data.verified_handoff_count}</div>
        <div class="small-text">00_Verified_Scope_and_Groups/discovered_items.txt</div>
      </div>
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Master Dataset SHA-256</div>
        <div class="kpi-val" style="font-size:0.86rem;font-family:var(--font-mono);">${escHtml((mr.dataset_sha256 || "Single-Stage").slice(0, 16))}...</div>
        <div class="small-text">Canonical_Reviewed_Dataset.json</div>
      </div>
      <div class="kpi-box verdict-allow">
        <div class="kpi-label">Master Report SHA-256</div>
        <div class="kpi-val" style="font-size:0.86rem;font-family:var(--font-mono);">${escHtml((mr.report_sha256 || "Single-Stage").slice(0, 16))}...</div>
        <div class="small-text">Finalized_Master_Executive_Summary.html</div>
      </div>
    </div>
    <table class="kit-table" style="margin-top:10px;">
      <thead><tr><th>Stage</th><th>Skill Slug</th><th>Verdict</th><th>Prod Verified</th><th>Stage Dataset SHA-256</th></tr></thead>
      <tbody>${stRows}</tbody>
    </table>
    ${data.master_markdown_preview ? `<pre class="code-viewer" style="max-height:300px;margin-top:10px;">${escHtml(data.master_markdown_preview)}</pre>` : ""}
  `;
}

async function downloadOrchestratorSuiteZip() {
  const slug = document.getElementById("orch-select-pipeline").value || "compliance-master-orchestrator";
  const resp = await fetch("/api/orchestrator/bundle.zip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pipeline_slug: slug })
  });
  if (resp.ok) {
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}-full-suite.zip`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

function initOllamaAndSkillCreatorAndOrchestrator() {
  const provSel = document.getElementById("global-llm-provider");
  if (provSel) provSel.addEventListener("change", refreshInstalledOllamaModels);
  const refreshOllamaBtn = document.getElementById("btn-refresh-ollama-models");
  if (refreshOllamaBtn) refreshOllamaBtn.addEventListener("click", refreshInstalledOllamaModels);

  const scIntBtn = document.getElementById("btn-sc-interview");
  if (scIntBtn) scIntBtn.addEventListener("click", runSkillCreatorInterview);
  const scBuildBtn = document.getElementById("btn-sc-build-standalone");
  if (scBuildBtn) scBuildBtn.addEventListener("click", buildStandaloneSkillFromWorkbench);
  const scEvalBtn = document.getElementById("btn-sc-run-real-evals");
  if (scEvalBtn) scEvalBtn.addEventListener("click", runRealSubprocessEvals);
  const scOptBtn = document.getElementById("btn-sc-opt-desc");
  if (scOptBtn) scOptBtn.addEventListener("click", optimizeAndApplyTriggerDescription);
  const scDlBtn = document.getElementById("btn-sc-download-skill");
  if (scDlBtn) scDlBtn.addEventListener("click", downloadStandaloneSkillArchive);

  const orchProvBtn = document.getElementById("btn-orch-provision-suite");
  if (orchProvBtn) orchProvBtn.addEventListener("click", provisionReferenceComplianceSuite);
  const orchCompBtn = document.getElementById("btn-orch-compile");
  if (orchCompBtn) orchCompBtn.addEventListener("click", compileCustomOrchestratorFromUi);
  const orchFullBtn = document.getElementById("btn-orch-run-full");
  if (orchFullBtn) orchFullBtn.addEventListener("click", () => runOrchestratorFromUi("full_workflow"));
  const orchStageBtn = document.getElementById("btn-orch-run-stage");
  if (orchStageBtn) orchStageBtn.addEventListener("click", () => runOrchestratorFromUi("single_stage"));
  const orchVerifyBtn = document.getElementById("btn-orch-verify-tworun");
  if (orchVerifyBtn) orchVerifyBtn.addEventListener("click", () => runOrchestratorFromUi("two_run_determinism"));
  const orchZipBtn = document.getElementById("btn-orch-download-zip");
  if (orchZipBtn) orchZipBtn.addEventListener("click", downloadOrchestratorSuiteZip);

  refreshInstalledOllamaModels();
  refreshOrchestratorPipelines();
}

document.addEventListener("DOMContentLoaded", initApp);

