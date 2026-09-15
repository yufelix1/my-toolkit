const reviewState = {
    scanId: null,
    root: "",
    games: [],
    emptyDirectories: [],
    summary: {},
    view: "recordings",
    filter: "",
};

const ROOT_STORAGE_KEY = "gameRecordingReview.rootPath";

const elements = {
    rootBadge: document.getElementById("root-badge"),
    refreshButton: document.getElementById("refresh-button"),
    openSettingsButton: document.getElementById("open-settings-button"),
    setupEmpty: document.getElementById("setup-empty"),
    setupButton: document.getElementById("setup-button"),
    status: document.getElementById("status"),
    content: document.getElementById("review-content"),
    gameCount: document.getElementById("game-count"),
    directoryCount: document.getElementById("directory-count"),
    recordingCount: document.getElementById("recording-count"),
    emptyCount: document.getElementById("empty-count"),
    recordingTabCount: document.getElementById("recording-tab-count"),
    emptyTabCount: document.getElementById("empty-tab-count"),
    filterInput: document.getElementById("filter-input"),
    gameGroups: document.getElementById("game-groups"),
    recordingsEmpty: document.getElementById("recordings-empty"),
    emptyView: document.getElementById("empty-view"),
    recordingsView: document.getElementById("recordings-view"),
    emptyDirectoryList: document.getElementById("empty-directory-list"),
    directoriesEmpty: document.getElementById("directories-empty"),
    emptyHeadingCount: document.getElementById("empty-heading-count"),
    cleanAllButton: document.getElementById("clean-all-button"),
    previewDialog: document.getElementById("preview-dialog"),
    previewVideo: document.getElementById("preview-video"),
    previewName: document.getElementById("preview-name"),
    previewLocation: document.getElementById("preview-location"),
    closePreviewButton: document.getElementById("close-preview-button"),
    settingsDialog: document.getElementById("settings-dialog"),
    settingsForm: document.getElementById("settings-form"),
    settingsRootPath: document.getElementById("settings-root-path"),
    settingsError: document.getElementById("settings-error"),
    closeSettingsButton: document.getElementById("close-settings-button"),
    cancelSettingsButton: document.getElementById("cancel-settings-button"),
    saveSettingsButton: document.getElementById("save-settings-button"),
    toast: document.getElementById("toast"),
};

let toastTimer;

elements.settingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    await scanRoot(elements.settingsRootPath.value.trim(), {fromSettings: true, persist: true});
});

elements.openSettingsButton.addEventListener("click", openSettings);
elements.setupButton.addEventListener("click", openSettings);
elements.closeSettingsButton.addEventListener("click", closeSettings);
elements.cancelSettingsButton.addEventListener("click", closeSettings);
elements.refreshButton.addEventListener("click", () => scanRoot(reviewState.root));

elements.filterInput.addEventListener("input", event => {
    reviewState.filter = event.target.value.trim().toLowerCase();
    renderRecordings();
    renderEmptyDirectories();
});

document.querySelectorAll(".view-tab").forEach(tab => {
    tab.addEventListener("click", () => setView(tab.dataset.view));
});

elements.cleanAllButton.addEventListener("click", async () => {
    const count = reviewState.emptyDirectories.length;
    if (!count || !confirm(`确定删除 ${count} 个空目录吗？此操作不可撤销。`)) return;
    await deleteEmptyDirectories();
});

elements.closePreviewButton.addEventListener("click", closePreview);
elements.previewDialog.addEventListener("close", stopPreview);
elements.previewDialog.addEventListener("click", event => {
    if (event.target === elements.previewDialog) closePreview();
});

initializeRoot();

async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || "请求失败");
    return data;
}

async function scanRoot(path, options = {}) {
    const {fromSettings = false, persist = false} = options;
    if (!path) {
        if (fromSettings) {
            showSettingsError("请输入录屏根目录");
            elements.settingsRootPath.focus();
        } else {
            showStatus("请先配置录屏根目录");
        }
        return false;
    }

    setScanning(true);
    hideStatus();
    hideSettingsError();
    try {
        const data = await requestJson("/tools/game-recording-review/api/scan", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({path}),
        });

        reviewState.scanId = data.scan_id;
        reviewState.root = data.root;
        reviewState.games = data.games;
        reviewState.emptyDirectories = data.empty_directories;
        reviewState.summary = data.summary;
        elements.settingsRootPath.value = data.root;
        elements.rootBadge.textContent = data.root;
        elements.setupEmpty.hidden = true;
        elements.content.hidden = false;
        renderAll();

        if (persist) saveRoot(data.root);
        if (elements.settingsDialog.open) elements.settingsDialog.close();

        if (data.errors.length) {
            showStatus(`扫描完成，但有 ${data.errors.length} 个路径无法读取：${data.errors.join("；")}`, "warning");
        }
        return true;
    } catch (error) {
        if (fromSettings) {
            showSettingsError(error.message);
        } else {
            reviewState.scanId = null;
            elements.content.hidden = true;
            elements.setupEmpty.hidden = false;
            elements.rootBadge.textContent = "录屏根目录不可用";
            showStatus(error.message);
        }
        return false;
    } finally {
        setScanning(false);
    }
}

function setScanning(scanning) {
    elements.refreshButton.disabled = scanning || !reviewState.root;
    elements.saveSettingsButton.disabled = scanning;
    elements.saveSettingsButton.textContent = scanning ? "正在扫描..." : "保存并扫描";
}

function initializeRoot() {
    const savedRoot = loadRoot();
    if (!savedRoot) {
        elements.setupEmpty.hidden = false;
        return;
    }

    elements.settingsRootPath.value = savedRoot;
    elements.rootBadge.textContent = savedRoot;
    scanRoot(savedRoot);
}

function openSettings() {
    elements.settingsRootPath.value = reviewState.root || loadRoot();
    hideSettingsError();
    elements.settingsDialog.showModal();
    elements.settingsRootPath.focus();
    elements.settingsRootPath.select();
}

function closeSettings() {
    elements.settingsDialog.close();
}

function showSettingsError(message) {
    elements.settingsError.hidden = false;
    elements.settingsError.textContent = message;
}

function hideSettingsError() {
    elements.settingsError.hidden = true;
    elements.settingsError.textContent = "";
}

function loadRoot() {
    try {
        return localStorage.getItem(ROOT_STORAGE_KEY) || "";
    } catch (error) {
        return "";
    }
}

function saveRoot(path) {
    try {
        localStorage.setItem(ROOT_STORAGE_KEY, path);
    } catch (error) {
        showStatus("目录已载入，但浏览器无法保存该设置", "warning");
    }
}

function showStatus(message, type = "error") {
    elements.status.hidden = false;
    elements.status.className = `review-status ${type}`;
    elements.status.textContent = message;
}

function hideStatus() {
    elements.status.hidden = true;
    elements.status.textContent = "";
}

function renderAll() {
    const summary = reviewState.summary;
    elements.gameCount.textContent = summary.game_count;
    elements.directoryCount.textContent = summary.directory_count;
    elements.recordingCount.textContent = summary.recording_count;
    elements.emptyCount.textContent = summary.empty_directory_count;
    elements.recordingTabCount.textContent = summary.recording_count;
    elements.emptyTabCount.textContent = summary.empty_directory_count;
    elements.emptyHeadingCount.textContent = summary.empty_directory_count;
    elements.cleanAllButton.disabled = summary.empty_directory_count === 0;
    renderRecordings();
    renderEmptyDirectories();
}

function recordingMatches(recording) {
    if (!reviewState.filter) return true;
    return [recording.game_id, recording.directory_id, recording.name]
        .some(value => value.toLowerCase().includes(reviewState.filter));
}

function renderRecordings() {
    elements.gameGroups.replaceChildren();
    let visibleCount = 0;

    reviewState.games.forEach(game => {
        const recordings = game.recordings.filter(recordingMatches);
        if (!recordings.length) return;
        visibleCount += recordings.length;

        const section = document.createElement("section");
        section.className = "game-group";

        const header = document.createElement("div");
        header.className = "game-group-header";
        const title = document.createElement("h2");
        title.textContent = game.game_id;
        const count = document.createElement("span");
        count.textContent = `${recordings.length} 个录屏`;
        header.append(title, count);

        const grid = document.createElement("div");
        grid.className = "recording-grid";
        recordings.forEach(recording => grid.appendChild(createRecordingCard(recording)));
        section.append(header, grid);
        elements.gameGroups.appendChild(section);
    });

    elements.recordingsEmpty.hidden = visibleCount > 0;
}

function createRecordingCard(recording) {
    const article = document.createElement("article");
    article.className = "recording-card";

    const coverButton = document.createElement("button");
    coverButton.className = "cover-button";
    coverButton.type = "button";
    coverButton.title = `预览 ${recording.name}`;
    coverButton.setAttribute("aria-label", `预览 ${recording.name}`);
    coverButton.addEventListener("click", () => openPreview(recording));

    if (recording.cover_path) {
        const image = document.createElement("img");
        image.src = mediaUrl(recording.cover_path);
        image.alt = `${recording.name} 封面`;
        image.loading = "lazy";
        coverButton.appendChild(image);
    } else {
        const placeholder = document.createElement("span");
        placeholder.className = "cover-placeholder";
        const icon = document.createElement("strong");
        icon.textContent = "▶";
        const label = document.createElement("span");
        label.textContent = "无封面";
        placeholder.append(icon, label);
        coverButton.appendChild(placeholder);
    }

    const playIndicator = document.createElement("span");
    playIndicator.className = "play-indicator";
    playIndicator.textContent = "▶";
    playIndicator.setAttribute("aria-hidden", "true");
    coverButton.appendChild(playIndicator);

    const info = document.createElement("div");
    info.className = "recording-info";
    const name = document.createElement("h3");
    name.textContent = recording.name;

    const meta = document.createElement("div");
    meta.className = "recording-meta";
    const date = document.createElement("span");
    date.textContent = formatDate(recording.mtime);
    const size = document.createElement("span");
    size.textContent = formatBytes(recording.size);
    meta.append(date, size);

    const directory = document.createElement("div");
    directory.className = "recording-directory";
    directory.title = recording.directory_path;
    directory.textContent = recording.directory_id;

    const actions = document.createElement("div");
    actions.className = "recording-actions";
    const previewButton = commandButton("预览", "secondary-button", () => openPreview(recording));
    const deleteButton = commandButton("删除", "delete-button", () => confirmDeleteRecording(recording));
    actions.append(previewButton, deleteButton);
    info.append(name, meta, directory, actions);
    article.append(coverButton, info);
    return article;
}

function renderEmptyDirectories() {
    elements.emptyDirectoryList.replaceChildren();
    const directories = reviewState.emptyDirectories.filter(directory => {
        if (!reviewState.filter) return true;
        return [directory.game_id, directory.directory_id, directory.path]
            .some(value => value.toLowerCase().includes(reviewState.filter));
    });

    directories.forEach(directory => {
        const row = document.createElement("div");
        row.className = "empty-directory-row";
        const gameId = document.createElement("strong");
        gameId.textContent = directory.game_id;
        const path = document.createElement("code");
        path.textContent = directory.directory_id;
        const deleteButton = commandButton("删除", "delete-button", async () => {
            if (confirm(`确定删除空目录 ${directory.path} 吗？`)) {
                await deleteEmptyDirectories(directory.path);
            }
        });
        row.append(gameId, path, deleteButton);
        elements.emptyDirectoryList.appendChild(row);
    });

    elements.emptyDirectoryList.hidden = directories.length === 0;
    elements.directoriesEmpty.hidden = directories.length > 0;
}

function commandButton(label, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
}

function setView(view) {
    reviewState.view = view;
    elements.recordingsView.hidden = view !== "recordings";
    elements.emptyView.hidden = view !== "empty";
    document.querySelectorAll(".view-tab").forEach(tab => {
        const active = tab.dataset.view === view;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
    });
}

function mediaUrl(relativePath) {
    const path = relativePath.split(/[\\/]/).map(encodeURIComponent).join("/");
    return `/tools/game-recording-review/media/${encodeURIComponent(reviewState.scanId)}/${path}`;
}

function openPreview(recording) {
    elements.previewName.textContent = recording.name;
    elements.previewLocation.textContent = `${recording.game_id} / ${recording.directory_id}`;
    elements.previewVideo.src = mediaUrl(recording.path);
    elements.previewDialog.showModal();
    elements.previewVideo.play().catch(() => {});
}

function closePreview() {
    elements.previewDialog.close();
}

function stopPreview() {
    elements.previewVideo.pause();
    elements.previewVideo.removeAttribute("src");
    elements.previewVideo.load();
}

async function confirmDeleteRecording(recording) {
    if (!confirm(`确定删除录屏 ${recording.name} 及其封面吗？此操作不可撤销。`)) return;
    try {
        await requestJson("/tools/game-recording-review/api/recording", {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                scan_id: reviewState.scanId,
                path: recording.path,
                size: recording.size,
                mtime_ns: recording.mtime_ns,
            }),
        });
        showToast("录屏已删除");
        await scanRoot(reviewState.root);
    } catch (error) {
        showStatus(error.message);
    }
}

async function deleteEmptyDirectories(path = null) {
    try {
        const data = await requestJson("/tools/game-recording-review/api/empty-directories", {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({scan_id: reviewState.scanId, path}),
        });
        if (data.errors.length) {
            showStatus(data.errors.join("；"), "warning");
        } else {
            showToast(data.message);
        }
        await scanRoot(reviewState.root);
    } catch (error) {
        showStatus(error.message);
    }
}

function showToast(message) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.hidden = false;
    toastTimer = setTimeout(() => {
        elements.toast.hidden = true;
    }, 2600);
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let value = bytes / 1024;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function formatDate(timestamp) {
    return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(timestamp * 1000));
}
