/**
 * SkillForge AI — Clean, Minimal 2-Step UI Controller
 * Step 1: Browse or Upload an Application from Your PC + Translate with Progress Bar
 * Step 2: View Created Skills & Their File Locations on Disk
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

// ============================================================================
// 1. PC FOLDER BROWSER & FILE UPLOAD
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
      listEl.innerHTML = `<div class="text-muted" style="padding:8px;">Use <strong>📁 Upload App Folder</strong> or <strong>📄 Upload App File(s)</strong> above to select an application from your PC.</div>`;
    }
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

    selectedAppName = data.app_name;
    selectedAppSource = data.combined_source;
    document.getElementById("skill-name-input").value = data.skill_slug;
    document.getElementById("selected-app-name").textContent = `${data.app_name} (${data.source_path})`;
    document.getElementById("selected-app-meta").textContent =
      `${data.files_scanned} file(s) scanned • ${data.routes_discovered.length} endpoints • ${data.functions_extracted.length} functions • ${data.tools_discovered.length} tools ready`;
    setProgress(100, `Loaded "${data.app_name}" — click "Convert Application into LLM Skill" below.`, true);
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
  setProgress(100, `Loaded ${files.length} file(s) — click "Convert Application into LLM Skill" below.`, true);
}

// ============================================================================
// 2. TRANSLATE APPLICATION INTO SKILL (WITH PROGRESS BAR)
// ============================================================================
async function convertApplicationToSkill() {
  const skillSlug = document.getElementById("skill-name-input").value.trim() || "custom-app-skill";
  const selectEl = document.getElementById("llm-profile-select");
  const prof = (selectEl && llmProfiles.find((p) => p.id === selectEl.value)) || llmProfiles[0] || { provider: "ollama", model: "llama3.2:3b", base_url: "http://127.0.0.1:11434" };
  const apiKey = document.getElementById("llm-apikey-input").value.trim();
  const btn = document.getElementById("btn-convert-skill");

  if (!selectedAppSource) {
    // If user hasn't clicked a folder yet, scan the currently browsed folder first
    if (currentBrowsePath) {
      await selectPcApplicationPath(currentBrowsePath);
    }
  }

  btn.disabled = true;
  setProgress(20, "Step 1/3 — Extracting application endpoints, functions, and tool schemas...", true);

  await new Promise((r) => setTimeout(r, 250));
  setProgress(55, `Step 2/3 — Translating application into LLM Skill via ${prof.name || prof.provider}...`, true);

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
    // Fallback to fast local compile
  }

  if (!compiled) {
    setProgress(75, "Step 2/3 — Compiling application routes and functions into skill files...", true);
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

  setProgress(90, "Step 3/3 — Saving SKILL.md and registering tools with the built-in MCP Server...", true);
  await loadCreatedSkills();
  setProgress(100, `✓ Done! Skill "${skillSlug}" created and saved to disk.`, true);
  btn.disabled = false;
}

// ============================================================================
// 3. CREATED SKILLS & FILE LOCATIONS ON DISK
// ============================================================================
async function loadCreatedSkills() {
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

  if (!workspaceSkills || workspaceSkills.length === 0) {
    listEl.innerHTML = `
      <div class="skill-card">
        <div class="text-muted">No skills created yet. Select any application on your PC on the left and click <strong>✨ Convert Application into LLM Skill</strong>.</div>
      </div>
    `;
    return;
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
              <span class="location-label">Skill Folder &amp; SKILL.md Location on Your PC:</span>
              <code class="location-path">${skillMdPath}</code>
              <div class="text-muted small-text">MCP Server: <code>${mcpPath}</code></div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm copy-path-btn" data-path="${skillDir}">
              📋 Copy Folder Path
            </button>
          </div>

          <div class="skill-tools-row">
            ${tools.slice(0, 8).map((t) => `<span class="tool-tag">🔧 ${t.name}</span>`).join("")}
            ${tools.length > 8 ? `<span class="text-muted small-text">+${tools.length - 8} more</span>` : ""}
          </div>

          <div class="skill-actions-row">
            <button type="button" class="btn btn-secondary btn-sm preview-skill-btn" data-slug="${s.name}">
              👁️ View SKILL.md
            </button>
            <button type="button" class="btn btn-primary btn-sm download-zip-btn" data-slug="${s.name}">
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

  listEl.querySelectorAll(".copy-path-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(btn.dataset.path);
      btn.textContent = "✓ Copied Path!";
      setTimeout(() => {
        btn.textContent = "📋 Copy Folder Path";
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
// 4. LLM CONNECTION MANAGER
// ============================================================================
async function loadLlmProfiles() {
  const selectEl = document.getElementById("llm-profile-select");
  const pill = document.getElementById("ollama-status-pill");
  try {
    const resp = await fetch("/api/llm/status");
    if (resp.ok) {
      const data = await resp.json();
      llmProfiles = data.profiles || [];
      if (data.ollama && data.ollama.connected) {
        pill.textContent = `Local Ollama Ready (${data.ollama.models.join(", ")})`;
        pill.className = "badge badge-emerald";
      } else {
        pill.textContent = `${llmProfiles.length} LLM Profiles Ready`;
        pill.className = "badge badge-accent";
      }
    }
  } catch (_) {
    llmProfiles = [{ id: "ollama-primary", name: "Local Ollama (llama3.2:3b)", provider: "ollama", model: "llama3.2:3b", base_url: "http://127.0.0.1:11434" }];
  }

  selectEl.innerHTML = llmProfiles
    .map((p) => `<option value="${p.id}">${p.name} (${p.model})</option>`)
    .join("");

  const updateKeyVisibility = () => {
    const prof = llmProfiles.find((p) => p.id === selectEl.value);
    const wrap = document.getElementById("api-key-wrap");
    if (wrap && prof) {
      wrap.style.display = prof.provider === "openai" || prof.provider === "anthropic" || prof.provider === "gemini" ? "block" : "none";
    }
  };
  selectEl.onchange = updateKeyVisibility;
  updateKeyVisibility();
}

function initApp() {
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

  document.getElementById("btn-save-new-llm").addEventListener("click", async () => {
    const name = document.getElementById("new-llm-name").value.trim();
    const provider = document.getElementById("new-llm-provider").value;
    const model = document.getElementById("new-llm-model").value.trim() || "llama3.2:3b";
    const base_url = document.getElementById("new-llm-url").value.trim();
    const api_key = document.getElementById("new-llm-key").value.trim();
    await fetch("/api/llm/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, provider, model, base_url, api_key })
    });
    document.getElementById("add-llm-drawer").style.display = "none";
    await loadLlmProfiles();
  });

  document.getElementById("btn-convert-skill").addEventListener("click", convertApplicationToSkill);

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
