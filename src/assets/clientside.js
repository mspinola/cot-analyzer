
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        scroll_to_bottom: function(children) {
            const logViewer = document.getElementById('server-log-viewer');
            if (logViewer) {
                // Delay slightly to allow Dash to render the new text
                setTimeout(() => {
                    logViewer.scrollTop = logViewer.scrollHeight;
                }, 50);
            }
            return window.dash_clientside.no_update;
        }
    }
});