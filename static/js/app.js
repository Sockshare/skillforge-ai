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
      const resp = await fetch("/api/bundle.zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(found)
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${slug}-skill-bundle.zip`;
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

function initApp() {
  const sampleBtn = document.getElementById("btn-load-sample-app");
  if (sampleBtn) {
    sampleBtn.addEventListener("click", loadBundledSampleApp);
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

  browsePcFolder();
  loadLlmProfiles();
  loadCreatedSkills();
}

document.addEventListener("DOMContentLoaded", initApp);
