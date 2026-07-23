
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        scroll_to_bottom: function (children) {
            const logViewer = document.getElementById('server-log-viewer');
            if (logViewer) {
                // Delay slightly to allow Dash to render the new text
                setTimeout(() => {
                    logViewer.scrollTop = logViewer.scrollHeight;
                }, 50);
            }
            return window.dash_clientside.no_update;
        },
        export_heatmap_csv: function(n_clicks) {
            if (n_clicks) {
                dash_ag_grid.getApiAsync("heatmap-matrix-grid").then(function(grid) {
                    if (grid) {
                        var today = new Date();
                        var yyyy = today.getFullYear();
                        var mm = String(today.getMonth() + 1).padStart(2, '0');
                        var dd = String(today.getDate()).padStart(2, '0');
                        var fileName = yyyy + '-' + mm + '-' + dd + '-cot-heatmap.csv';
                        grid.exportDataAsCsv({ fileName: fileName });
                    }
                });
            }
            return window.dash_clientside.no_update;
        },
        export_oi_alignment_image: function(n_clicks, asset_name) {
            if (n_clicks) {
                if (typeof html2canvas === 'undefined') {
                    console.error("html2canvas library is not loaded.");
                    return window.dash_clientside.no_update;
                }
                
                var signalPanel = document.getElementById("oi_alignment_signal_panel");
                var dashGraphDiv = document.getElementById("oi_alignment_main_graph");
                
                if (!signalPanel || !dashGraphDiv || typeof Plotly === 'undefined') {
                    console.error("Could not find signal panel or plot div.");
                    return window.dash_clientside.no_update;
                }

                var plotNode = dashGraphDiv.querySelector('.js-plotly-plot') || dashGraphDiv;

                var w = Math.round(plotNode.getBoundingClientRect().width) || 1200;
                var base_h = Math.round(plotNode.getBoundingClientRect().height) || 800;
                
                // Artificially stretch the height for the export to give subplots breathing room
                var h = Math.max(Math.round(base_h * 1.5), 1200);

                Plotly.toImage(plotNode, {format: 'png', width: w, height: h}).then(function(dataUrl) {
                    // Create an off-screen container to stitch the DOM together cleanly
                    var exportContainer = document.createElement('div');
                    exportContainer.style.position = 'absolute';
                    exportContainer.style.left = '-9999px';
                    exportContainer.style.top = '-9999px';
                    // Match the width of the active signal panel
                    exportContainer.style.width = signalPanel.clientWidth + 'px'; 
                    exportContainer.style.backgroundColor = '#1a1a1a';
                    exportContainer.style.padding = '20px';
                    exportContainer.style.display = 'flex';
                    exportContainer.style.flexDirection = 'column';
                    exportContainer.style.gap = '20px';
                    exportContainer.id = 'temp-export-container';

                    // Clone the signal panel HTML
                    var clonedSignalPanel = signalPanel.cloneNode(true);
                    exportContainer.appendChild(clonedSignalPanel);

                    // Create the static image of the plot
                    var plotImg = document.createElement('img');
                    plotImg.style.width = '100%';
                    plotImg.style.height = 'auto';
                    plotImg.style.borderRadius = '4px';
                    plotImg.style.border = '1px solid rgba(171, 184, 201, 0.2)';
                    
                    plotImg.onload = function() {
                        exportContainer.appendChild(plotImg);
                        
                        // Append to theme-container so it inherits all CSS styles natively
                        var themeContainer = document.getElementById("theme-container") || document.body;
                        themeContainer.appendChild(exportContainer);

                        // Give DOM time to calculate layout
                        setTimeout(function() {
                            html2canvas(exportContainer, {
                                backgroundColor: "#1a1a1a",
                                scale: 2, 
                                useCORS: true,
                                logging: false
                            }).then(function(canvas) {
                                themeContainer.removeChild(exportContainer);
                                var link = document.createElement('a');
                                var today = new Date();
                                var dateStr = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
                                var titleEl = document.getElementById('oi_alignment_signal_card_title');
                                var assetPrefix = "";
                                var rawTitle = "";
                                if (titleEl) {
                                    rawTitle = titleEl.innerText || titleEl.textContent || "";
                                }
                                if (!rawTitle && asset_name) {
                                    rawTitle = asset_name;
                                }
                                
                                if (rawTitle) {
                                    // Sanitize string e.g. "Gold (GC)" -> "gold_gc"
                                    assetPrefix = rawTitle.replace(/[^a-z0-9]/gi, '_').replace(/_+/g, '_').toLowerCase();
                                    if (assetPrefix.endsWith('_')) assetPrefix = assetPrefix.slice(0, -1);
                                    if (assetPrefix.startsWith('_')) assetPrefix = assetPrefix.slice(1);
                                    if (assetPrefix.length > 0) assetPrefix += "_";
                                }
                                link.download = assetPrefix + 'oi_alignment_' + dateStr + '.png';
                                link.href = canvas.toDataURL("image/png");
                                link.click();
                            }).catch(function(err) {
                                console.error("html2canvas failed on cloned DOM: ", err);
                                if (document.getElementById('temp-export-container')) {
                                    themeContainer.removeChild(exportContainer);
                                }
                            });
                        }, 150);
                    };
                    plotImg.src = dataUrl;
                }).catch(function(err) {
                    console.error("Plotly toImage failed", err);
                });
            }
            return window.dash_clientside.no_update;
        },
        /**
         * Rescale every y-axis to the data actually visible in the current x-window.
         *
         * Shared by every stacked-plot page. `graphId` is the Dash id of the graph to
         * act on, passed as State so one implementation serves them all.
         *
         * This used to be a server callback on OI Alignment. It fires on every pan and
         * zoom, and it shipped the whole figure up and back each time to do arithmetic
         * the browser already had the data for. Nothing here needs the server: the
         * traces are in the figure, and the answer is their min and max in the window.
         *
         * Returns the rightmost visible date, which OI Alignment's signal panel reads to
         * follow the right edge of the chart. Pages with no such panel simply leave that
         * store unread.
         */
        autoscale_y_axes: function(relayoutData, graphId) {
            var noUpdate = window.dash_clientside.no_update;
            if (!relayoutData || !graphId) { return noUpdate; }

            var gd = document.querySelector('#' + graphId + ' .js-plotly-plot');
            if (!gd || !gd.data || typeof Plotly === 'undefined') { return noUpdate; }
            var figure = {data: gd.data, layout: gd.layout};

            // Plotly does not always send a numeric column as a plain array. Anything
            // it can pack goes over the wire base64-encoded as {dtype, bdata}, which
            // indexes as undefined if you treat it like a list. This is what silently
            // broke the server-side version: every trace raised, the bare except
            // swallowed it, and the axes simply never moved.
            var DTYPES = {
                f8: Float64Array, f4: Float32Array,
                i4: Int32Array, i2: Int16Array, i1: Int8Array,
                u4: Uint32Array, u2: Uint16Array, u1: Uint8Array
            };
            function asArray(v) {
                if (!v) { return null; }
                if (Array.isArray(v) || ArrayBuffer.isView(v)) { return v; }
                // Plotly keeps a decoded copy when it has one; prefer it over redoing
                // the work on every pan.
                if (v._inputArray) { return v._inputArray; }
                var T = v.bdata && DTYPES[v.dtype];
                if (!T) { return null; }
                try {
                    var bin = atob(v.bdata);
                    var bytes = new Uint8Array(bin.length);
                    for (var i = 0; i < bin.length; i++) { bytes[i] = bin.charCodeAt(i); }
                    return new T(bytes.buffer);
                } catch (e) {
                    return null;
                }
            }

            var layout = figure.layout;
            var key;
            var update = {};

            // The axes that actually exist, taken from the traces rather than from the
            // layout keys. `autosize` also fires while a figure is being swapped, and at
            // that moment the layout can still carry the previous figure's axis list. A
            // relayout naming an axis this graph no longer has throws inside Plotly
            // ("cannot read properties of undefined (reading '_inputDomain')").
            function axisKeyOf(trace) {
                var a = trace.yaxis || 'y';
                return a === 'y' ? 'yaxis' : 'yaxis' + a.slice(1);
            }
            var liveAxes = {};
            (figure.data || []).forEach(function(t) { liveAxes[axisKeyOf(t)] = true; });

            // Reset Axes, Autoscale, or a double-click: hand each axis back to Plotly.
            if ('xaxis.autorange' in relayoutData || 'autosize' in relayoutData) {
                for (key in liveAxes) {
                    if (layout[key]) { update[key + '.autorange'] = true; }
                }
                if (Object.keys(update).length) {
                    try { Plotly.relayout(gd, update); } catch (e) { return noUpdate; }
                }
                // Tell the server the window is back to the whole history. The stamp
                // makes two consecutive resets distinct values, so the second still
                // fires.
                return {xEnd: null, stamp: Date.now()};
            }

            var xStart = null, xEnd = null;
            for (key in relayoutData) {
                var v = relayoutData[key];
                if (key.indexOf('xaxis') !== 0) { continue; }
                if (key.slice(-8) === 'range[0]') { xStart = v; }
                else if (key.slice(-8) === 'range[1]') { xEnd = v; }
                else if (key.slice(-5) === 'range' && Array.isArray(v) && v.length === 2) {
                    xStart = v[0]; xEnd = v[1];
                }
            }
            if (xStart === null || xEnd === null) { return noUpdate; }

            var t0 = new Date(xStart).getTime();
            var t1 = new Date(xEnd).getTime();
            if (isNaN(t0) || isNaN(t1)) { return noUpdate; }

            var ranges = {};
            (figure.data || []).forEach(function(trace) {
                var xs = asArray(trace.x);
                if (!xs || !xs.length) { return; }

                // Candlesticks carry their extremes on high/low rather than y.
                var isCandle = trace.type === 'candlestick';
                var hi = asArray(isCandle ? trace.high : trace.y);
                var lo = asArray(isCandle ? trace.low : trace.y);
                if (!hi || !lo) { return; }

                var lo_v = Infinity, hi_v = -Infinity, seen = false;
                for (var i = 0; i < xs.length; i++) {
                    var t = new Date(xs[i]).getTime();
                    if (isNaN(t) || t < t0 || t > t1) { continue; }
                    var a = lo[i], b = hi[i];
                    if (a === null || b === null || a === undefined || b === undefined) { continue; }
                    if (isNaN(a) || isNaN(b)) { continue; }
                    if (a < lo_v) { lo_v = a; }
                    if (b > hi_v) { hi_v = b; }
                    seen = true;
                }
                if (!seen) { return; }

                var axis = trace.yaxis || 'y';
                var axisKey = axis === 'y' ? 'yaxis' : 'yaxis' + axis.slice(1);
                if (!(axisKey in ranges)) { ranges[axisKey] = [lo_v, hi_v]; }
                else {
                    ranges[axisKey][0] = Math.min(ranges[axisKey][0], lo_v);
                    ranges[axisKey][1] = Math.max(ranges[axisKey][1], hi_v);
                }
            });

            for (var axisKey in ranges) {
                var r = ranges[axisKey];
                if (r[0] === r[1]) { continue; }
                var pad = (r[1] - r[0]) * 0.05;
                if (pad === 0) { pad = r[0] !== 0 ? Math.abs(r[0] * 0.05) : 1; }
                update[axisKey + '.range'] = [r[0] - pad, r[1] + pad];
                update[axisKey + '.autorange'] = false;
            }
            // Only y-axis keys go in, so the relayoutData this fires carries no x-range
            // and the next pass falls out at the parse step. That is what stops it
            // chasing its own tail.
            if (Object.keys(update).length) {
                try { Plotly.relayout(gd, update); } catch (e) { return noUpdate; }
            }

            // The rightmost visible date, for the panel below the chart.
            //
            // It travels on this store rather than the server reading relayoutData
            // itself, because the Plotly.relayout above fires a *second* relayoutData
            // milliseconds later carrying the y-axis keys. A server callback listening
            // to relayoutData is superseded by that second event and its answer is
            // dropped before it reaches the DOM. Only a real x-zoom writes here, so
            // nothing supersedes it.
            return {xEnd: String(xEnd), stamp: Date.now()};
        }
    }
});

var dagcomponentfuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

dagcomponentfuncs.SignalBadgesRenderer = function(props) {
    if (!props.value) {
        return React.createElement('span', null, "");
    }
    const sigs = props.value.split(", ");
    return React.createElement('div', 
        {style: {display: 'flex', gap: '4px', flexWrap: 'wrap', alignItems: 'center', height: '100%'}},
        sigs.map((sig, idx) => {
            let colorClass = "badge-neutral";
            if (sig.includes("BULL") || sig.includes("BUY") || sig.includes("SQZ")) {
                colorClass = "badge-bull";
            } else if (sig.includes("BEAR") || sig.includes("SELL") || sig.includes("EXHAUSTION") || sig.includes("CAPITULATION")) {
                colorClass = "badge-bear";
            }
            return React.createElement('span', {key: idx, className: `badge-pill ${colorClass}`}, sig);
        })
    );
};

dagcomponentfuncs.MomentumRenderer = function(props) {
    if (props.value === null || props.value === undefined) {
        return React.createElement('span', null, "");
    }
    const val = parseFloat(props.value);
    
    const maxThreshold = props.maxThreshold !== undefined ? props.maxThreshold : 40;
    const minThreshold = props.minThreshold !== undefined ? props.minThreshold : -40;
    
    let color = props.neutralColor || "var(--bs-body-color)"; // Neutral text color
    let prefix = "";
    
    if (val >= maxThreshold) {
        color = "#10B981"; // BULL_COLOR
        prefix = "▲ +";
    } else if (val <= minThreshold) {
        color = "#EF4444"; // BEAR_COLOR
        prefix = "▼ -";
    } else {
        // Values within thresholds: neutral color, NO arrows
        if (val > 0) {
            prefix = "+";
        } else if (val < 0) {
            prefix = "-";
        } else {
            prefix = "";
        }
    }
    
    // Use formatted value if available, stripping the leading +, -, or Unicode minus (\u2212)
    let text = props.valueFormatted ? props.valueFormatted.replace(/^[+\-\u2212\s]+/, '') : Math.abs(val);
    
    return React.createElement('span', {style: {color: color, fontWeight: '500'}}, prefix + text);
};

dagcomponentfuncs.MLProgressBarRenderer = function(props) {
    if (props.value === null || props.value === undefined) {
        return React.createElement('span', null, "");
    }
    const val = parseFloat(props.value);
    
    let barColor = "rgba(147, 161, 161, 0.2)"; // Neutral
    let textColor = props.neutralColor || "var(--bs-body-color)";
    let fontWeight = "500";
    
    if (val >= 55) {
        barColor = "rgba(16, 185, 129, 0.3)"; // Bullish
        textColor = "#10B981";
        fontWeight = "bold";
    } else if (val >= 50) {
        barColor = "rgba(16, 185, 129, 0.3)"; // Bullish
        textColor = "#10B981";
    }
    
    const text = props.valueFormatted || val + "%";

    return React.createElement('div', {
        style: {
            width: '100%',
            height: '100%',
            position: 'relative',
            display: 'flex',
            alignItems: 'center'
        }
    }, [
        React.createElement('div', {
            key: 'bar',
            style: {
                position: 'absolute',
                left: 0,
                top: '4px',
                bottom: '4px',
                width: Math.min(Math.max(val, 0), 100) + '%',
                backgroundColor: barColor,
                borderRadius: '2px',
                transition: 'width 0.3s ease'
            }
        }),
        React.createElement('span', {
            key: 'text',
            style: {
                position: 'relative',
                zIndex: 1,
                fontWeight: fontWeight,
                color: textColor,
                paddingLeft: '4px'
            }
        }, text)
    ]);
};

dagcomponentfuncs.DataBarRenderer = function(props) {
    if (props.value === null || props.value === undefined) {
        return React.createElement('span', null, "");
    }
    const val = parseFloat(props.value);
    
    const logVal = Math.log10(Math.abs(val) + 1);
    const maxLog = props.maxAbsValue ? Math.log10(props.maxAbsValue + 1) : 5;
    const isBull = val >= 0;
    
    // Percentage width clamped between 0 and 100
    let pct = Math.min(Math.max((logVal / maxLog) * 100, 0), 100);
    
    // Give it a minimum width if there's any momentum at all
    if (Math.abs(val) > 0 && pct < 5) pct = 5;
    
    // Use format or raw value
    const text = props.valueFormatted ? props.valueFormatted : val;
    
    // Determine bar color
    const color = isBull ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)";
    const textColor = isBull ? "#10B981" : "#EF4444";
    
    // We create a relative container with a background bar and foreground text
    return React.createElement(
        'div',
        {
            style: {
                position: 'relative',
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end', // AG Grid typically right-aligns numbers
                paddingRight: '8px'
            }
        },
        [
            React.createElement('div', {
                key: 'bar',
                style: {
                    position: 'absolute',
                    top: '4px',
                    bottom: '4px',
                    right: isBull ? 'auto' : '0',
                    left: isBull ? '0' : 'auto',
                    width: `${pct}%`,
                    backgroundColor: color,
                    borderRadius: '2px',
                    zIndex: 0
                }
            }),
            React.createElement('span', {
                key: 'text',
                style: {
                    position: 'relative',
                    zIndex: 1,
                    color: (Math.abs(val) > (props.minThreshold || 0)) ? textColor : "var(--bs-body-color)"
                }
            }, text)
        ]
    );
};