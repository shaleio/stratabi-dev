// assets/monaco_init.js
self.MonacoEnvironment = {
  getWorkerUrl: function (moduleId, label) {
    switch (label) {
      case "json":
        return "/assets/monaco/vs/assets/json.worker.js";
      case "editor":
        return "/assets/monaco/vs/assets/editor.worker.js";
      case "css":
        return "/assets/monaco/vs/assets/css.worker.js";
      case "html":
        return "/assets/monaco/vs/assets/html.worker.js";
      case "typescript":
      case "javascript":
        return "/assets/monaco/vs/assets/ts.worker.js";
      default:
        return "/assets/monaco/vs/assets/editor.worker.js";
    }
  }
};

