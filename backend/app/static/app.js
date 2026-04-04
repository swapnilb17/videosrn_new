(function () {
  const body = document.body;
  const chat = document.getElementById("chat");
  const form = document.getElementById("form");
  const topicEl = document.getElementById("topic");
  const langEl = document.getElementById("language");
  const submitBtn = document.getElementById("submit");
  const logoInput = document.getElementById("logo");
  const assetProductInput = document.getElementById("asset-product");
  const assetThumbnailInput = document.getElementById("asset-thumbnail");
  const assetCtaInput = document.getElementById("asset-cta");
  const assetAddressEl = document.getElementById("asset-address");
  const assetsModal = document.getElementById("assets-modal");
  const assetsTrigger = document.getElementById("assets-trigger");
  const assetsClose = document.getElementById("assets-close");
  const assetsCancel = document.getElementById("assets-cancel");
  const assetsDone = document.getElementById("assets-done");
  const assetsBackdrop = document.getElementById("assets-backdrop");
  const assetsSummary = document.getElementById("assets-summary");
  const logoFilenameEl = document.getElementById("logo-filename");
  const productFilenameEl = document.getElementById("product-filename");
  const thumbnailFilenameEl = document.getElementById("thumbnail-filename");
  const ctaFilenameEl = document.getElementById("cta-filename");

  const pickIdToFilenameEl = {
    logo: logoFilenameEl,
    "asset-product": productFilenameEl,
    "asset-thumbnail": thumbnailFilenameEl,
    "asset-cta": ctaFilenameEl,
  };
  const enhanceMotionEl = document.getElementById("enhance-motion");
  const statusEl = document.getElementById("status");
  const configBanner = document.getElementById("config-banner");
  const headerAuth = document.getElementById("header-auth");
  const authLogout = document.getElementById("auth-logout");
  const authUser = document.getElementById("auth-user");
  const authLoading = document.getElementById("auth-loading");
  const authGate = document.getElementById("auth-gate");
  const authGateError = document.getElementById("auth-gate-error");
  const voiceField = document.getElementById("voice-field");
  const voicePicker = document.getElementById("voice-picker");
  const voiceTrigger = document.getElementById("voice-trigger");
  const voiceTriggerLabel = document.getElementById("voice-trigger-label");
  const voicePanel = document.getElementById("voice-panel");
  const voiceList = document.getElementById("voice-list");

  var oauthEnabled = false;
  var oauthSignedIn = false;
  var oauthUserEmail = "";
  var welcomeInjected = false;
  var googleTtsUiEnabled = false;
  var voiceSelection = "";
  var voiceSelectionDisplay = "Auto";
  var previewAudio = null;
  var previewObjectUrl = null;
  var voicePanelOpen = false;

  function stopPreviewAudio() {
    if (previewAudio) {
      try {
        previewAudio.pause();
      } catch (e) {
        /* ignore */
      }
      previewAudio = null;
    }
    if (previewObjectUrl) {
      try {
        URL.revokeObjectURL(previewObjectUrl);
      } catch (e2) {
        /* ignore */
      }
      previewObjectUrl = null;
    }
    document.querySelectorAll(".voice-picker-play.is-playing").forEach(function (n) {
      n.classList.remove("is-playing");
    });
  }

  function setVoicePanelOpen(open) {
    voicePanelOpen = !!open;
    if (voicePanel) voicePanel.hidden = !voicePanelOpen;
    if (voiceTrigger) voiceTrigger.setAttribute("aria-expanded", voicePanelOpen ? "true" : "false");
    if (voicePicker) voicePicker.classList.toggle("is-open", voicePanelOpen);
    if (!voicePanelOpen) stopPreviewAudio();
  }

  function formatGenderLabel(g) {
    var s = String(g || "").toLowerCase();
    if (s === "male") return "Male";
    if (s === "female") return "Female";
    if (s === "neutral") return "Neutral";
    if (s === "unspecified") return "—";
    return "—";
  }

  function updateVoiceSelectionUi() {
    if (!voiceTriggerLabel) return;
    var t = voiceSelectionDisplay || "Auto";
    voiceTriggerLabel.textContent = t.length > 26 ? t.slice(0, 24) + "…" : t;
  }

  function markVoiceRowsSelected() {
    document.querySelectorAll(".voice-picker-row").forEach(function (row) {
      var v = row.getAttribute("data-voice") || "";
      row.classList.toggle("is-selected", v === voiceSelection);
    });
  }

  function selectVoiceValue(name, friendlyLabel) {
    voiceSelection = (name || "").trim();
    if (!voiceSelection) {
      voiceSelectionDisplay = "Auto";
    } else {
      var fl = friendlyLabel != null ? String(friendlyLabel).trim() : "";
      voiceSelectionDisplay = fl || voiceSelection;
    }
    updateVoiceSelectionUi();
    markVoiceRowsSelected();
    setVoicePanelOpen(false);
  }

  function playPreviewSvg() {
    return (
      '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>'
    );
  }

  function previewVoiceSample(voiceName, playBtn) {
    if (!voiceName || !langEl) return;
    var lang = langEl.value || "en";
    var url =
      "/api/tts/preview.mp3?voice=" +
      encodeURIComponent(voiceName) +
      "&language=" +
      encodeURIComponent(lang);
    stopPreviewAudio();
    if (playBtn) playBtn.classList.add("is-playing");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) {
          return r.text().then(function (t) {
            var err = t;
            try {
              var j = JSON.parse(t);
              if (j.detail) err = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
            } catch (e) {
              /* use raw */
            }
            throw new Error(err || r.statusText);
          });
        }
        return r.blob();
      })
      .then(function (blob) {
        previewObjectUrl = URL.createObjectURL(blob);
        previewAudio = new Audio(previewObjectUrl);
        previewAudio.addEventListener("ended", function () {
          if (playBtn) playBtn.classList.remove("is-playing");
        });
        previewAudio.addEventListener("error", function () {
          if (playBtn) playBtn.classList.remove("is-playing");
        });
        return previewAudio.play();
      })
      .catch(function (err) {
        if (playBtn) playBtn.classList.remove("is-playing");
        var msg = err && err.message ? err.message : String(err);
        if (statusEl) statusEl.textContent = "Voice preview failed: " + msg.slice(0, 120);
      });
  }

  function canLoadTtsVoices() {
    if (!googleTtsUiEnabled) return false;
    if (oauthEnabled && !oauthSignedIn) return false;
    return true;
  }

  function loadVoicesForLanguage() {
    if (!voiceList || !langEl) return;
    if (!canLoadTtsVoices()) {
      voiceList.innerHTML = "";
      return;
    }
    var lang = langEl.value || "en";
    fetch("/api/tts/voices?language=" + encodeURIComponent(lang), {
      credentials: "same-origin",
    })
      .then(function (r) {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      })
      .then(function (data) {
        voiceList.innerHTML = "";
        if (!data || !data.available || !Array.isArray(data.voices)) return;
        data.voices.forEach(function (v) {
          if (!v || !v.name) return;
          var friendly = (v.label && String(v.label).trim()) || v.name;
          var row = document.createElement("div");
          row.className = "voice-picker-row";
          row.setAttribute("role", "option");
          row.setAttribute("tabindex", "0");
          row.setAttribute("data-voice", v.name);
          row.setAttribute("data-label", friendly);

          var main = document.createElement("span");
          main.className = "voice-picker-row-main";

          var playBtn = document.createElement("button");
          playBtn.type = "button";
          playBtn.className = "voice-picker-play";
          playBtn.setAttribute("aria-label", "Play preview: " + friendly);
          playBtn.innerHTML = playPreviewSvg();
          playBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            previewVoiceSample(v.name, playBtn);
          });

          var nameSpan = document.createElement("span");
          nameSpan.className = "voice-picker-name";
          nameSpan.textContent = friendly;

          main.appendChild(playBtn);
          main.appendChild(nameSpan);

          var g = document.createElement("span");
          g.className = "voice-picker-gender";
          g.textContent = formatGenderLabel(v.gender);

          row.appendChild(main);
          row.appendChild(g);

          row.addEventListener("click", function () {
            selectVoiceValue(v.name, friendly);
          });
          row.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              selectVoiceValue(v.name, friendly);
            }
          });

          voiceList.appendChild(row);
        });
        markVoiceRowsSelected();
      })
      .catch(function () {
        voiceList.innerHTML = "";
      });
  }

  function syncVoiceFieldVisibility() {
    if (!voiceField) return;
    var show = googleTtsUiEnabled && (!oauthEnabled || oauthSignedIn);
    voiceField.hidden = !show;
    if (!show) {
      setVoicePanelOpen(false);
      voiceSelection = "";
      voiceSelectionDisplay = "Auto";
      updateVoiceSelectionUi();
      return;
    }
    loadVoicesForLanguage();
  }

  if (voiceTrigger && voicePanel) {
    voiceTrigger.addEventListener("click", function (e) {
      e.stopPropagation();
      setVoicePanelOpen(!voicePanelOpen);
    });
  }

  document.addEventListener("click", function () {
    if (voicePanelOpen) setVoicePanelOpen(false);
  });

  if (voicePanel) {
    voicePanel.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && voicePanelOpen) {
      setVoicePanelOpen(false);
    }
  });

  var autoRow = document.querySelector(".voice-picker-row-auto");
  if (autoRow) {
    autoRow.addEventListener("click", function () {
      selectVoiceValue("", "Auto");
    });
    autoRow.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectVoiceValue("", "Auto");
      }
    });
  }

  if (langEl) {
    langEl.addEventListener("change", function () {
      voiceSelection = "";
      voiceSelectionDisplay = "Auto";
      updateVoiceSelectionUi();
      markVoiceRowsSelected();
      loadVoicesForLanguage();
    });
  }

  if (/[?&]auth_error=1(?:&|$)/.test(window.location.search || "")) {
    if (authGateError) {
      authGateError.hidden = false;
      authGateError.textContent =
        "Google sign-in did not complete. Please try again with Continue with Google.";
    }
    try {
      history.replaceState({}, "", window.location.pathname);
    } catch (e) {
      /* ignore */
    }
  }

  function applyAuthShell() {
    body.classList.remove("auth-resolving", "auth-public", "auth-needs-login", "auth-in-app");
    if (authLoading) authLoading.setAttribute("aria-busy", "false");

    if (!oauthEnabled) {
      body.classList.add("auth-public");
      if (authGate) authGate.hidden = true;
      if (headerAuth) headerAuth.hidden = true;
      injectWelcomeOnce();
      syncVoiceFieldVisibility();
      return;
    }

    if (oauthSignedIn) {
      body.classList.add("auth-in-app");
      if (authGate) authGate.hidden = true;
      if (headerAuth) headerAuth.hidden = false;
      if (authUser) authUser.textContent = oauthUserEmail;
      if (submitBtn) submitBtn.disabled = false;
      injectWelcomeOnce();
      syncVoiceFieldVisibility();
      return;
    }

    body.classList.add("auth-needs-login");
    if (authGate) authGate.hidden = false;
    if (headerAuth) headerAuth.hidden = true;
    syncVoiceFieldVisibility();
  }

  function injectWelcomeOnce() {
    if (welcomeInjected || !chat) return;
    welcomeInjected = true;
    appendTextMessage(
      "assistant",
      "Hi — I turn a topic into an educational video: script, narration, and MP4. Choose duration, language, and topic; open Assets for optional logo, product image, address, thumbnail, or a CTA closing slide with your buy message. Turn on Enhance for slide zoom plus a two-voice dialogue. Tap Generate video when ready.",
    );
  }

  fetch("/health")
    .then(function (r) {
      return r.json();
    })
    .then(function (h) {
      if (!h) {
        oauthEnabled = false;
        oauthSignedIn = false;
        googleTtsUiEnabled = false;
        applyAuthShell();
        syncVoiceFieldVisibility();
        return;
      }
      oauthEnabled = !!h.google_oauth_enabled;
      oauthSignedIn = !!(h.google_user_email && String(h.google_user_email).trim());
      oauthUserEmail = oauthSignedIn ? String(h.google_user_email).trim() : "";
      applyAuthShell();

      googleTtsUiEnabled = h.google_tts_ready === true;
      syncVoiceFieldVisibility();

      if (!configBanner) return;
      var parts = [];
      if (h.openai_ready === false) {
        parts.push("Script generation is not configured for this server.");
      }
      var voiceReady =
        h.google_tts_ready === true ||
        h.elevenlabs_ready === true;
      if (!voiceReady) {
        parts.push("Voice generation is not configured for this server.");
      }
      if (h.ffmpeg_ready === false) {
        parts.push("Video encoding is not available on this server (missing encoder).");
      }
      var coreReady =
        h.openai_ready !== false &&
        voiceReady &&
        h.ffmpeg_ready !== false;
      if (
        coreReady &&
        h.gemini_native_image_ready === false &&
        h.gemini_imagen_ready === false &&
        h.nano_banana_ready === false
      ) {
        parts.push("Optional: slide-style visuals are not enabled — videos will use a simple title screen.");
      }
      if (parts.length) {
        configBanner.hidden = false;
        configBanner.textContent = parts.join(" ");
      }
    })
    .catch(function () {
      oauthEnabled = false;
      oauthSignedIn = false;
      googleTtsUiEnabled = false;
      applyAuthShell();
      syncVoiceFieldVisibility();
    });

  const STEPS = [
    "Writing your script…",
    "Creating narration…",
    "Creating visuals…",
    "Building your video…",
  ];

  function el(tag, className, html) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function appendMessage(role, innerNodes) {
    const wrap = el("div", "msg " + role);
    const label = el("div", "msg-label", role === "user" ? "You" : "LearnCast");
    const body = el("div", "msg-body");
    if (Array.isArray(innerNodes)) innerNodes.forEach((c) => body.appendChild(c));
    else body.appendChild(innerNodes);
    wrap.appendChild(label);
    wrap.appendChild(body);
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
    return wrap;
  }

  function appendTextMessage(role, text) {
    const p = el("p", null);
    p.textContent = text;
    return appendMessage(role, p);
  }

  function showTyping() {
    const wrap = el("div", "msg assistant");
    wrap.id = "typing-indicator";
    const label = el("div", "msg-label", "LearnCast");
    const body = el("div", "msg-body");
    const typing = el("div", "typing");
    typing.appendChild(el("span"));
    typing.appendChild(el("span"));
    typing.appendChild(el("span"));
    body.appendChild(typing);
    wrap.appendChild(label);
    wrap.appendChild(body);
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  }

  function removeTyping() {
    document.getElementById("typing-indicator")?.remove();
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function describeTargetDuration(sec) {
    var n = Number(sec);
    if (!Number.isFinite(n) || n <= 0) n = 59;
    if (n === 90) return "about 1.5 minutes";
    if (n < 60) return "about " + n + " seconds";
    var mins = n / 60;
    if (mins === Math.floor(mins)) return "about " + mins + " minutes";
    return "about " + mins + " minutes";
  }

  function renderResult(data) {
    const card = el("div", "result-card");
    const intro = el("p", null);
    var durLabel = describeTargetDuration(data.target_duration_seconds);
    intro.innerHTML =
      "<strong>Done.</strong> Here is your " +
      escapeHtml(durLabel) +
      " educational piece — hook, facts, and outro, with voice and video.";
    if (data.video_width && data.video_height) {
      intro.innerHTML +=
        " Output <strong>" +
        escapeHtml(String(data.video_width)) +
        "×" +
        escapeHtml(String(data.video_height)) +
        "</strong>";
      var outBits = [];
      if (data.content_format_applied) {
        outBits.push(escapeHtml(String(data.content_format_applied).replace(/_/g, " ")));
      }
      if (data.output_quality_applied) {
        outBits.push(escapeHtml(String(data.output_quality_applied)));
      }
      if (outBits.length) {
        intro.innerHTML += " (" + outBits.join(" · ") + ")";
      }
      intro.innerHTML += ".";
    }
    card.appendChild(intro);

    const hook = el("div", "result-section");
    hook.innerHTML = "<h3>Hook</h3><p>" + escapeHtml(data.script.hook) + "</p>";
    card.appendChild(hook);

    const facts = el("div", "result-section");
    const ul = document.createElement("ul");
    (data.script.facts || []).forEach((f) => {
      const li = document.createElement("li");
      li.textContent = f;
      ul.appendChild(li);
    });
    const h = document.createElement("h3");
    h.textContent = "Key facts";
    facts.appendChild(h);
    facts.appendChild(ul);
    card.appendChild(facts);

    const end = el("div", "result-section");
    end.innerHTML = "<h3>Closing</h3><p>" + escapeHtml(data.script.ending) + "</p>";
    card.appendChild(end);

    const videoWrap = el("div", "video-wrap");
    const video = document.createElement("video");
    video.setAttribute("controls", "");
    video.setAttribute("playsinline", "");
    video.setAttribute("preload", "metadata");
    video.src = data.mp4_url;
    videoWrap.appendChild(video);

    const toolbar = el("div", "video-toolbar");
    const fsBtn = document.createElement("button");
    fsBtn.type = "button";
    fsBtn.className = "btn-video-fs";
    fsBtn.textContent = "Fullscreen";
    fsBtn.setAttribute("aria-label", "Play video in fullscreen");
    fsBtn.addEventListener("click", function () {
      try {
        if (video.requestFullscreen) {
          void video.requestFullscreen();
          return;
        }
        if (typeof video.webkitEnterFullscreen === "function") {
          video.webkitEnterFullscreen();
        }
      } catch (err) {
        /* ignore — browser may block without user gesture (should not happen here) */
      }
    });
    toolbar.appendChild(fsBtn);
    videoWrap.appendChild(toolbar);

    card.appendChild(videoWrap);

    function mediaDownloadHref(base) {
      if (!base) return base;
      var sep = base.indexOf("?") >= 0 ? "&" : "?";
      return base + sep + "attachment=1";
    }

    const actions = el("div", "actions");
    const aMp4 = el("a", "btn-link", "Download MP4");
    aMp4.href = mediaDownloadHref(data.mp4_url);
    aMp4.setAttribute("download", "learncast-" + data.job_id + ".mp4");
    const aMp3 = el("a", "btn-link secondary", "Download MP3");
    aMp3.href = mediaDownloadHref(data.mp3_url);
    aMp3.setAttribute("download", "learncast-" + data.job_id + ".mp3");
    actions.appendChild(aMp4);
    actions.appendChild(aMp3);
    card.appendChild(actions);

    appendMessage("assistant", card);
  }

  function setLoading(loading, stepIndex) {
    submitBtn.disabled = loading;
    submitBtn.classList.toggle("loading", loading);
    if (loading) {
      statusEl.textContent = STEPS[stepIndex] || STEPS[0];
    } else {
      statusEl.textContent = "";
    }
  }

  let stepTimer = null;
  function startStepAnimation() {
    let i = 0;
    setLoading(true, 0);
    stepTimer = window.setInterval(() => {
      i = Math.min(i + 1, STEPS.length - 1);
      statusEl.textContent = STEPS[i];
    }, 8000);
  }

  function stopStepAnimation() {
    if (stepTimer) {
      clearInterval(stepTimer);
      stepTimer = null;
    }
    setLoading(false, 0);
  }

  function setAssetsModalOpen(open) {
    if (!assetsModal) return;
    var on = !!open;
    assetsModal.hidden = !on;
    assetsModal.setAttribute("aria-hidden", on ? "false" : "true");
    if (body) body.classList.toggle("assets-modal-open", on);
    if (on) {
      if (assetsDone) {
        assetsDone.focus();
      } else if (assetsClose) {
        assetsClose.focus();
      }
    } else if (assetsTrigger) {
      assetsTrigger.focus();
    }
  }

  function syncAssetFilename(pickId) {
    var inp = document.getElementById(pickId);
    var el = pickIdToFilenameEl[pickId];
    if (!inp || !el) return;
    var f = inp.files && inp.files[0];
    el.textContent = f ? f.name : "";
  }

  function syncAllAssetFilenames() {
    syncAssetFilename("logo");
    syncAssetFilename("asset-product");
    syncAssetFilename("asset-thumbnail");
    syncAssetFilename("asset-cta");
  }

  function countSelectedAssets() {
    var n = 0;
    if (logoInput && logoInput.files && logoInput.files[0]) n++;
    if (assetProductInput && assetProductInput.files && assetProductInput.files[0]) n++;
    if (assetThumbnailInput && assetThumbnailInput.files && assetThumbnailInput.files[0]) n++;
    if (assetCtaInput && assetCtaInput.files && assetCtaInput.files[0]) n++;
    if (assetAddressEl && assetAddressEl.value.trim()) n++;
    return n;
  }

  function syncAssetsSummary() {
    if (!assetsSummary) return;
    var n = countSelectedAssets();
    if (n === 0) assetsSummary.textContent = "";
    else assetsSummary.textContent = n === 1 ? "1 added" : n + " added";
  }

  function clearAssetInputs() {
    if (logoInput) logoInput.value = "";
    if (assetProductInput) assetProductInput.value = "";
    if (assetThumbnailInput) assetThumbnailInput.value = "";
    if (assetCtaInput) assetCtaInput.value = "";
    if (assetAddressEl) assetAddressEl.value = "";
  }

  if (assetsTrigger) {
    assetsTrigger.addEventListener("click", function () {
      setAssetsModalOpen(true);
    });
  }
  function closeAssetsModal() {
    setAssetsModalOpen(false);
  }
  if (assetsClose) {
    assetsClose.addEventListener("click", closeAssetsModal);
  }
  if (assetsCancel) {
    assetsCancel.addEventListener("click", closeAssetsModal);
  }
  if (assetsDone) {
    assetsDone.addEventListener("click", closeAssetsModal);
  }
  if (assetsBackdrop) {
    assetsBackdrop.addEventListener("click", function () {
      setAssetsModalOpen(false);
    });
  }
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" && assetsModal && !assetsModal.hidden) {
      setAssetsModalOpen(false);
    }
  });

  document.querySelectorAll(".btn-asset-pick").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-pick");
      if (!id) return;
      var inp = document.getElementById(id);
      if (inp) inp.click();
    });
  });
  document.querySelectorAll(".btn-asset-clear").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.getAttribute("data-clear");
      if (!id) return;
      var inp = document.getElementById(id);
      if (inp) inp.value = "";
      syncAssetFilename(id);
      syncAssetsSummary();
    });
  });
  [logoInput, assetProductInput, assetThumbnailInput, assetCtaInput].forEach(function (inp) {
    if (inp) {
      inp.addEventListener("change", function () {
        syncAssetFilename(inp.id);
        syncAssetsSummary();
      });
    }
  });
  if (assetAddressEl) {
    assetAddressEl.addEventListener("input", syncAssetsSummary);
  }
  syncAllAssetFilenames();
  syncAssetsSummary();

  function syncEnhanceMotionAria() {
    if (!enhanceMotionEl) return;
    enhanceMotionEl.setAttribute("aria-checked", enhanceMotionEl.checked ? "true" : "false");
  }
  if (enhanceMotionEl) {
    enhanceMotionEl.addEventListener("change", syncEnhanceMotionAria);
    syncEnhanceMotionAria();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const topic = topicEl.value.trim();
    const language = langEl.value;
    var durationSelect = form.querySelector('select[name="target_duration_seconds"]');
    const targetDurationSeconds =
      durationSelect && durationSelect.value ? String(durationSelect.value) : "59";
    var formatSelect = form.querySelector('select[name="content_format"]');
    var qualitySelect = form.querySelector('select[name="output_quality"]');
    if (!topic) return;
    if (oauthEnabled && !oauthSignedIn) {
      return;
    }

    var assetCount = countSelectedAssets();
    var logoFile = logoInput && logoInput.files && logoInput.files[0];
    var productFile = assetProductInput && assetProductInput.files && assetProductInput.files[0];
    var thumbFile = assetThumbnailInput && assetThumbnailInput.files && assetThumbnailInput.files[0];
    var ctaFile = assetCtaInput && assetCtaInput.files && assetCtaInput.files[0];
    var addressVal = assetAddressEl && assetAddressEl.value.trim();
    var durTxt =
      durationSelect && durationSelect.selectedOptions && durationSelect.selectedOptions[0]
        ? durationSelect.selectedOptions[0].textContent.trim()
        : "";
    var voiceBit =
      googleTtsUiEnabled && voiceSelection
        ? " · Voice: " + (voiceSelectionDisplay || voiceSelection)
        : "";
    var enhanceBit =
      enhanceMotionEl && enhanceMotionEl.checked ? " · Enhance on" : "";
    var assetsBit =
      assetCount > 0 ? " · " + assetCount + " optional asset" + (assetCount === 1 ? "" : "s") : "";
    var formatTxt =
      formatSelect && formatSelect.selectedOptions && formatSelect.selectedOptions[0]
        ? formatSelect.selectedOptions[0].textContent.trim()
        : "";
    var qualityTxt =
      qualitySelect && qualitySelect.selectedOptions && qualitySelect.selectedOptions[0]
        ? qualitySelect.selectedOptions[0].textContent.trim()
        : "";
    var formatQualityBit =
      formatTxt || qualityTxt
        ? " · " +
          (formatTxt || "Format") +
          (qualityTxt ? " · " + qualityTxt : "")
        : "";
    appendTextMessage(
      "user",
      topic +
        (durTxt ? " · " + durTxt : "") +
        formatQualityBit +
        voiceBit +
        enhanceBit +
        assetsBit,
    );
    topicEl.value = "";
    clearAssetInputs();
    syncAllAssetFilenames();
    syncAssetsSummary();
    showTyping();
    startStepAnimation();

    try {
      const fd = new FormData();
      fd.append("topic", topic);
      fd.append("language", language);
      fd.append("target_duration_seconds", targetDurationSeconds);
      fd.append(
        "enhance_motion",
        enhanceMotionEl && enhanceMotionEl.checked ? "true" : "false",
      );
      if (logoFile) {
        fd.append("logo", logoFile);
      }
      if (productFile) {
        fd.append("product_image", productFile);
      }
      if (ctaFile) {
        fd.append("cta_image", ctaFile);
      }
      if (thumbFile) {
        fd.append("thumbnail_image", thumbFile);
      }
      if (addressVal) {
        fd.append("address", addressVal);
      }
      if (googleTtsUiEnabled && voiceSelection) {
        fd.append("google_tts_voice", voiceSelection);
      }
      if (formatSelect && formatSelect.value) {
        fd.append("content_format", formatSelect.value);
      }
      if (qualitySelect && qualitySelect.value) {
        fd.append("output_quality", qualitySelect.value);
      }
      const res = await fetch("/generate", {
        method: "POST",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        body: fd,
      });
      removeTyping();
      stopStepAnimation();

      const raw = await res.text();
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        throw new Error(raw.slice(0, 200) || "Invalid response");
      }

      if (!res.ok) {
        var detail =
          typeof data.detail === "string"
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map((d) => d.msg || d).join("; ")
              : res.statusText;
        if (res.status === 401 && /google/i.test(detail)) {
          detail += " Please sign in again with Continue with Google.";
        }
        const errWrap = el("div", "msg error");
        errWrap.innerHTML =
          '<div class="msg-label">Something went wrong</div><div class="msg-body">' +
          escapeHtml(detail) +
          "</div>";
        chat.appendChild(errWrap);
        chat.scrollTop = chat.scrollHeight;
        return;
      }

      renderResult(data);
    } catch (err) {
      removeTyping();
      stopStepAnimation();
      var msg = err && err.message ? err.message : String(err);
      if (/failed to fetch/i.test(msg)) {
        msg +=
          " — The browser never got an HTTP response. Typical causes: nginx not proxying POST /generate (or upstream down), TLS/cert issues, security group, or the request timing out before the proxy responds. Check DevTools → Network for the /generate row; on the server, tail nginx error.log and journalctl for the app.";
      }
      const errWrap = el("div", "msg error");
      errWrap.innerHTML =
        '<div class="msg-label">Could not complete request</div><div class="msg-body">' +
        escapeHtml(msg) +
        "</div>";
      chat.appendChild(errWrap);
      chat.scrollTop = chat.scrollHeight;
    }
  });
})();
