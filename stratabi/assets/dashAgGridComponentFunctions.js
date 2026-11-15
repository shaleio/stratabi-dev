/* StrataBI AG Grid cell renderers (dash-ag-grid looks them up by name in column_defs).
 *
 * StrataCopyCell — one-line, ellipsized text with a small "Copy" button that puts the FULL value on
 * the clipboard (hover shows it too). For long values like error messages:
 *   {"field": "Error", "cellRenderer": "StrataCopyCell"}
 */
var dagcomponentfuncs = (window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {});

(function () {
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // http:// (non-localhost) pages have no Clipboard API: fall back to a hidden textarea.
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy") ? resolve() : reject(new Error("copy failed")); }
      catch (e) { reject(e); }
      finally { document.body.removeChild(ta); }
    });
  }

  dagcomponentfuncs.StrataCopyCell = function (props) {
    var value = props.value === null || props.value === undefined ? "" : String(props.value);
    var state = React.useState("Copy");
    var label = state[0], setLabel = state[1];
    if (!value) { return null; }
    function onClick(e) {
      e.stopPropagation();
      copyText(value).then(function () { setLabel("Copied"); },
                           function () { setLabel("Copy failed"); });
      setTimeout(function () { setLabel("Copy"); }, 1500);
    }
    return React.createElement("span", { className: "sbi-copy-cell", title: value },
      React.createElement("button", { type: "button", className: "sbi-copy-btn", onClick: onClick }, label),
      React.createElement("span", { className: "sbi-copy-text" }, value));
  };
})();
