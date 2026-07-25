// assets/stratabi_monaco_init.js
(function () {
  let editorInstance = null;
  let editorContainer = null;
  let currentModel = null;

  function syncHiddenTextarea(value) {
    const ta = document.getElementById("monaco-hidden-textarea");
    if (ta) {
      ta.value = value;
      ta.dispatchEvent(new Event("input", { bubbles: true }));
      ta.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function attachChangeListener() {
    if (!editorInstance || !currentModel) return;

    currentModel.onDidChangeContent(() => {
      syncHiddenTextarea(editorInstance.getValue());
    });
  }

  function disposeEditor() {
    if (editorInstance) {
      editorInstance.dispose();
      editorInstance = null;
    }

    if (currentModel) {
      currentModel.dispose();
      currentModel = null;
    }

    editorContainer = null;
  }

  window.StratabiMonaco = {
    init: function ({ schema, initialValue, containerId }) {
      const container = document.getElementById(containerId);

      if (!container) {
        console.error("[StratabiMonaco] container not found:", containerId);
        return;
      }

      if (typeof require === "undefined") {
        console.error("[StratabiMonaco] require() not found. Is loader.js loaded?");
        return;
      }

      const startingText =
        typeof initialValue === "string"
          ? initialValue
          : JSON.stringify(initialValue ?? {}, null, 2);

      require(["vs/editor/editor.main"], function () {
        setTimeout(() => {
          /*
            Dash page navigation can recreate #monaco-container.
            If the container changed, the old Monaco instance is attached
            to a dead DOM node. Dispose and recreate.
          */
          if (editorInstance && editorContainer !== container) {
            disposeEditor();
          }

          if (!editorInstance) {
            currentModel = monaco.editor.createModel(startingText, "json");

            const _themeEl = document.getElementById("stratabi-editor-theme");
            const _editorTheme =
              (_themeEl && _themeEl.dataset && _themeEl.dataset.theme) || "vs-dark";

            editorInstance = monaco.editor.create(container, {
              model: currentModel,
              language: "json",
              theme: _editorTheme,
              automaticLayout: true,
              minimap: { enabled: false },
            });

            monaco.editor.setTheme(_editorTheme);

            editorContainer = container;

            container.addEventListener("mousedown", () => {
              if (editorInstance) {
                editorInstance.focus();
              }
            });

            attachChangeListener();
          } else {
            editorInstance.setValue(startingText);
          }

          syncHiddenTextarea(startingText);
          editorInstance.focus();

          const status = document.getElementById("builder-editor-status");
          if (status) {
            status.textContent = "Editor ready";
          }
        }, 0);
      });
    },

    getValue: function () {
      return editorInstance ? editorInstance.getValue() : "";
    },

    setValue: function (text) {
      const value = text || "";

      if (editorInstance) {
        editorInstance.setValue(value);
      }

      syncHiddenTextarea(value);
    },

    dispose: function () {
      disposeEditor();
    }
  };
})();