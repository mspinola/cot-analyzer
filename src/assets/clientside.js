
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
        /**
         * The Crowding Strip as one PNG: caption, legend and every column.
         *
         * Same shape as export_oi_alignment_image below and different in three ways,
         * each forced by what this page is.
         *
         * One, the strip lives in a fixed-height box that scrolls (the control card is
         * sticky, so the page itself must not scroll). A screenshot of that box is the
         * visible rows only, which is the opposite of what this page is for. The clone
         * gets height:auto and overflow:visible, so the export is the WHOLE board even
         * when the reader can only see a third of it.
         *
         * Two, there can be one column or two, so the plots are collected rather than
         * named. Each is snapshotted at its own on-screen size: the figure's height is
         * ROW_PX times its row count, so stretching it the way the OI export does would
         * change the row pitch, which is the one dimension on this figure that has to
         * stay constant between the two columns.
         *
         * Three, the caption and the legend are page chrome here rather than part of a
         * figure, and both carry things the picture cannot: the report date, which
         * window each row was measured over, and what the marks mean. An export without
         * them is a board of coloured dots with no date on it, so they are inside the
         * cloned container rather than added back afterwards.
         */
        export_strip_image: function(n_clicks, model_key, target_date) {
            if (!n_clicks) { return window.dash_clientside.no_update; }
            if (typeof html2canvas === 'undefined' || typeof Plotly === 'undefined') {
                console.error("html2canvas or Plotly is not loaded.");
                return window.dash_clientside.no_update;
            }
            var container = document.getElementById("strip_export_container");
            if (!container) {
                console.error("Could not find the strip export container.");
                return window.dash_clientside.no_update;
            }

            var plots = Array.prototype.slice.call(
                container.querySelectorAll('.js-plotly-plot'));
            if (!plots.length) { return window.dash_clientside.no_update; }

            // scale 2 for a crisp raster; the <img> is sized back down to the on-screen
            // width below, so the extra pixels land as resolution rather than as size.
            var shots = plots.map(function(node) {
                var box = node.getBoundingClientRect();
                return Plotly.toImage(node, {
                    format: 'png',
                    width: Math.round(box.width) || 900,
                    height: Math.round(box.height) || 800,
                    scale: 2
                }).then(function(dataUrl) {
                    return {url: dataUrl, width: Math.round(box.width) || 900};
                });
            });

            Promise.all(shots).then(function(images) {
                var clone = container.cloneNode(true);
                clone.style.position = 'absolute';
                clone.style.left = '-9999px';
                clone.style.top = '-9999px';
                clone.style.width = container.clientWidth + 'px';
                clone.style.backgroundColor = '#1a1a1a';
                clone.style.padding = '20px';

                // Every scroll box in the clone opens up, so the export carries rows
                // the reader would have had to scroll to.
                Array.prototype.forEach.call(
                    clone.querySelectorAll('*'), function(node) {
                        if (node.style && (node.style.overflowY || node.style.overflow)) {
                            node.style.overflow = 'visible';
                            node.style.overflowY = 'visible';
                            node.style.height = 'auto';
                            node.style.maxHeight = 'none';
                        }
                    });

                // And so does every fold. The legend and the caption sit in a collapse
                // that is shut by default, and they are the only things saying what
                // week this is and what the marks mean, so a PNG without them is a
                // board of coloured dots. The fold is about screen space; it has no
                // business deciding what a shared image contains.
                Array.prototype.forEach.call(
                    clone.querySelectorAll('.collapse'), function(node) {
                        node.classList.add('show');
                        node.style.height = 'auto';
                        node.style.visibility = 'visible';
                    });

                // Swap each live plot for its snapshot, in the same order and in place,
                // so the column layout the page chose is the layout the PNG gets.
                var clonePlots = Array.prototype.slice.call(
                    clone.querySelectorAll('.js-plotly-plot'));
                var pending = [];
                clonePlots.forEach(function(node, i) {
                    if (!images[i]) { return; }
                    var img = document.createElement('img');
                    img.style.width = images[i].width + 'px';
                    img.style.maxWidth = '100%';
                    img.style.height = 'auto';
                    img.style.display = 'block';
                    pending.push(new Promise(function(resolve) {
                        img.onload = resolve;
                        img.onerror = resolve;
                    }));
                    img.src = images[i].url;
                    node.parentNode.replaceChild(img, node);
                });

                var themeContainer = document.getElementById("theme-container")
                    || document.body;
                themeContainer.appendChild(clone);

                // html2canvas measures rather than waits, so a decoded image is a
                // precondition, not a nicety: an <img> still loading paints as nothing.
                Promise.all(pending).then(function() {
                    setTimeout(function() {
                        html2canvas(clone, {
                            backgroundColor: "#1a1a1a",
                            scale: 2,
                            useCORS: true,
                            logging: false
                        }).then(function(canvas) {
                            themeContainer.removeChild(clone);
                            var stamp = target_date;
                            if (!stamp) {
                                var today = new Date();
                                stamp = today.getFullYear() + '-'
                                    + String(today.getMonth() + 1).padStart(2, '0') + '-'
                                    + String(today.getDate()).padStart(2, '0');
                            }
                            var model = (model_key || 'model')
                                .replace(/[^a-z0-9]/gi, '_').toLowerCase();
                            var link = document.createElement('a');
                            link.download = 'cot_strip_' + model + '_' + stamp + '.png';
                            link.href = canvas.toDataURL("image/png");
                            link.click();
                        }).catch(function(err) {
                            console.error("html2canvas failed on the strip clone: ", err);
                            if (clone.parentNode === themeContainer) {
                                themeContainer.removeChild(clone);
                            }
                        });
                    }, 150);
                });
            }).catch(function(err) {
                console.error("Plotly toImage failed on the strip", err);
            });

            return window.dash_clientside.no_update;
        },
        /**
         * The Divergence board as one PNG: caption, teaching and the whole table.
         *
         * Same family as export_strip_image above, with two differences forced by
         * what this page is. There is no Plotly on it: the board is an HTML table
         * and the sparklines are data-URI images, so the clone IS the picture and
         * no snapshot pass is needed. And the clone is sized to the widest thing
         * SCROLLING inside the container rather than to the container: on a phone
         * the table pans sideways in its own box, and a clone at container width
         * would export the clipped view that scroll box exists to avoid.
         *
         * Buttons are removed from the clone rather than kept outside the
         * container: the help fold's toggle lives inside it by design (the fold is
         * part of the page), and a control in a picture is the one thing on it
         * that cannot be acted on.
         */
        export_divergence_image: function(n_clicks, target_date) {
            if (!n_clicks) { return window.dash_clientside.no_update; }
            if (typeof html2canvas === 'undefined') {
                console.error("html2canvas is not loaded.");
                return window.dash_clientside.no_update;
            }
            var container = document.getElementById("divergence_export_container");
            if (!container) {
                console.error("Could not find the divergence export container.");
                return window.dash_clientside.no_update;
            }

            var width = container.clientWidth;
            Array.prototype.forEach.call(
                container.querySelectorAll('*'), function(node) {
                    if (node.scrollWidth > width) { width = node.scrollWidth; }
                });

            var clone = container.cloneNode(true);
            clone.style.position = 'absolute';
            clone.style.left = '-9999px';
            clone.style.top = '-9999px';
            clone.style.width = (width + 40) + 'px';
            clone.style.backgroundColor = '#1a1a1a';
            clone.style.padding = '20px';

            // Scroll boxes open up, so the export carries the columns and rows a
            // small screen could only reach by panning.
            Array.prototype.forEach.call(
                clone.querySelectorAll('*'), function(node) {
                    if (node.style && (node.style.overflowX || node.style.overflow)) {
                        node.style.overflow = 'visible';
                        node.style.overflowX = 'visible';
                        node.style.maxHeight = 'none';
                    }
                });
            // And the folds, the strip export's rule: the teaching is the only
            // thing saying what the emphasis and the threshold rule mean, so the
            // PNG carries it whether or not the reader ever opened it.
            Array.prototype.forEach.call(
                clone.querySelectorAll('.collapse'), function(node) {
                    node.classList.add('show');
                    node.style.height = 'auto';
                    node.style.visibility = 'visible';
                });
            Array.prototype.forEach.call(
                clone.querySelectorAll('button'), function(node) {
                    node.parentNode.removeChild(node);
                });

            var themeContainer = document.getElementById("theme-container")
                || document.body;
            themeContainer.appendChild(clone);
            setTimeout(function() {
                html2canvas(clone, {
                    backgroundColor: "#1a1a1a",
                    scale: 2,
                    useCORS: true,
                    logging: false
                }).then(function(canvas) {
                    themeContainer.removeChild(clone);
                    var stamp = target_date;
                    if (!stamp) {
                        var today = new Date();
                        stamp = today.getFullYear() + '-'
                            + String(today.getMonth() + 1).padStart(2, '0') + '-'
                            + String(today.getDate()).padStart(2, '0');
                    }
                    var link = document.createElement('a');
                    link.download = 'cot_divergence_' + stamp + '.png';
                    link.href = canvas.toDataURL("image/png");
                    link.click();
                }).catch(function(err) {
                    console.error("html2canvas failed on the divergence clone: ", err);
                    if (clone.parentNode === themeContainer) {
                        themeContainer.removeChild(clone);
                    }
                });
            }, 150);

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

            // A figure may ship its own rules in layout.meta.refit: which axes are
            // fitted at all, and the ratio at which a price panel earns a log scale.
            // Exposure does, because two of its panels are pinned to 0-100 on the
            // percentile scale and must not be fitted to a zoomed window, and because
            // its price panel has to re-decide log against linear for the range now on
            // screen. Figures without it behave exactly as they did.
            var spec = (layout.meta || {}).refit || null;
            if (spec) {
                for (key in liveAxes) {
                    if (spec.axes.indexOf(key) === -1) { delete liveAxes[key]; }
                }
            }

            // Reset Axes, Autoscale, or a double-click: hand each axis back to Plotly.
            //
            // `autosize` is grouped here but is NOT one of those gestures. It fires on
            // first paint and on every window resize, where the reader has asked for
            // nothing. Resetting on it threw away any range the server had computed
            // before the reader ever saw it, which is why panels that fit their axis
            // to the visible window server-side (get_net_pos_plot, and the category
            // panels) still opened autoranged over their whole history.
            //
            // So on a resize, leave an explicitly ranged axis alone. Plotly reports
            // autorange === true only for an axis it is ranging itself; one given an
            // explicit range carries no autorange key at all. A genuine reset still
            // hands back everything, including those.
            var isReset = 'xaxis.autorange' in relayoutData;
            if (isReset && spec) {
                // Not autorange. A zoom may have switched the price panel to linear,
                // and handing the axis back to Plotly would leave it there: autorange
                // restores the RANGE and has no opinion about the TYPE. Re-fitting over
                // the whole series reaches the answer the server drew in the first
                // place, by the same rule.
                fitAxes(-Infinity, Infinity);
                return {xEnd: null, stamp: Date.now()};
            }
            if (isReset || 'autosize' in relayoutData) {
                for (key in liveAxes) {
                    if (!layout[key]) { continue; }
                    if (!isReset && layout[key].autorange !== true) { continue; }
                    update[key + '.autorange'] = true;
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

            fitAxes(t0, t1);

            // The rightmost visible date, for the panel below the chart.
            //
            // It travels on this store rather than the server reading relayoutData
            // itself, because the Plotly.relayout above fires a *second* relayoutData
            // milliseconds later carrying the y-axis keys. A server callback listening
            // to relayoutData is superseded by that second event and its answer is
            // dropped before it reaches the DOM. Only a real x-zoom writes here, so
            // nothing supersedes it.
            return {xEnd: String(xEnd), stamp: Date.now()};

            // Fit every live axis to the points between t0 and t1. Called with infinite
            // bounds to fit the whole series, which is what a reset needs on a figure
            // whose price panel decides its own scale.
            function fitAxes(t0, t1) {
                var ranges = {};
                (figure.data || []).forEach(function(trace) {
                    var axisKey = axisKeyOf(trace);
                    if (!(axisKey in liveAxes)) { return; }
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

                    if (!(axisKey in ranges)) { ranges[axisKey] = [lo_v, hi_v]; }
                    else {
                        ranges[axisKey][0] = Math.min(ranges[axisKey][0], lo_v);
                        ranges[axisKey][1] = Math.max(ranges[axisKey][1], hi_v);
                    }
                });

                for (var axisKey in ranges) {
                    var r = ranges[axisKey];
                    if (spec && axisKey === spec.price_axis) {
                        priceAxis(update, axisKey, r[0], r[1], spec);
                        continue;
                    }
                    if (r[0] === r[1]) { continue; }
                    var pad = (r[1] - r[0]) * 0.05;
                    if (pad === 0) { pad = r[0] !== 0 ? Math.abs(r[0] * 0.05) : 1; }
                    update[axisKey + '.range'] = [r[0] - pad, r[1] + pad];
                    update[axisKey + '.autorange'] = false;
                }
                // Only y-axis keys go in, so the relayoutData this fires carries no
                // x-range and the next pass falls out at the parse step. That is what
                // stops it chasing its own tail.
                if (Object.keys(update).length) {
                    try { Plotly.relayout(gd, update); } catch (e) { return; }
                }
            }
        }
    }
});

// A price panel that decides its own scale, for the window actually on screen.
//
// Mirrors price_axis_type and log_ticks in components/exposure_traces.py, and takes the
// threshold from the figure rather than repeating the number here. Log earns its place
// on a RATIO, so a window too narrow to show one goes back to linear rather than keeping
// a curvature it no longer has the range to express, and the ticks are rebuilt for the
// decades on screen instead of the ones the whole series spans.
function priceAxis(update, axis, min, max, spec) {
    var useLog = min > 0 && max / min >= spec.log_ratio_min;
    update[axis + '.type'] = useLog ? 'log' : 'linear';
    update[axis + '.autorange'] = false;
    var pad;
    if (!useLog) {
        pad = (max - min) * spec.pad;
        if (pad === 0) { pad = min !== 0 ? Math.abs(min * spec.pad) : 1; }
        update[axis + '.range'] = [min - pad, max + pad];
        update[axis + '.tickmode'] = 'auto';
        update[axis + '.tickvals'] = null;
        update[axis + '.ticktext'] = null;
        return;
    }
    // A log axis takes its range in log10 units, and so does the padding: a twentieth of
    // a decade above a series is not a twentieth of its value.
    var lo = Math.log10(min), hi = Math.log10(max);
    pad = (hi - lo) * spec.pad;
    if (pad === 0) { pad = spec.pad; }
    update[axis + '.range'] = [lo - pad, hi + pad];

    var values = [];
    for (var e = Math.floor(lo); Math.pow(10, e) <= max; e++) {
        [1, 2, 5].forEach(function(mantissa) {
            var value = mantissa * Math.pow(10, e);
            if (value >= min && value <= max) { values.push(value); }
        });
    }
    // Fewer than three is a range too narrow to label by hand, which is the same bar
    // log_ticks sets. Plotly's own labels beat two lonely gridlines.
    if (values.length >= 3) {
        update[axis + '.tickmode'] = 'array';
        update[axis + '.tickvals'] = values;
        update[axis + '.ticktext'] = values.map(function(v) {
            return v.toLocaleString(undefined, {maximumFractionDigits: 0});
        });
    } else {
        update[axis + '.tickmode'] = 'auto';
        update[axis + '.tickvals'] = null;
        update[axis + '.ticktext'] = null;
    }
}


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
/**
 * A contribution bar that diverges from the CENTRE of the cell.
 *
 * DataBarRenderer above anchors its bar on the left and colours it by sign, which is
 * right for a momentum column where every row is asking "how much". This column asks
 * something else: each row is a market's share of a signed total, so the reader wants
 * to see at a glance which markets carry the total and which lean against it. A
 * left-anchored bar shows a dissenting market as a short bar, the same shape as a small
 * agreeing one; a centred bar shows it pointing the other way, which is what it is
 * doing.
 *
 * Colour follows the leg, not the sign, because the leg is already the page's colour
 * and the sign is already carried by the direction the bar points. A market pointing
 * against the total is faded rather than recoloured, matching the figure this replaced:
 * "opposite" is one variable and the hue is already spending itself on which leg this
 * is.
 *
 * Params, from cellRendererParams: `maxAbs` (the largest absolute contribution in the
 * table, so every row is drawn to one scale), `totalSign` (+1 or -1, which decides what
 * "against" means, since on a net-short total the negative markets are the ones
 * agreeing), and `withColor` / `againstColor`.
 */
dagcomponentfuncs.ContributionBarRenderer = function(props) {
    if (props.value === null || props.value === undefined || isNaN(props.value)) {
        return React.createElement('span', null, "");
    }
    var val = parseFloat(props.value);
    var maxAbs = parseFloat(props.maxAbs) || 0;
    if (!(maxAbs > 0)) { maxAbs = Math.abs(val) || 1; }

    var totalSign = (parseFloat(props.totalSign) || 1) >= 0 ? 1 : -1;
    var agrees = (val >= 0 ? 1 : -1) === totalSign;
    var color = agrees ? (props.withColor || 'rgba(96,165,250,0.85)')
                       : (props.againstColor || 'rgba(96,165,250,0.30)');

    // Half the cell per side, so a bar at maxAbs reaches the edge and no further.
    var half = Math.min(Math.abs(val) / maxAbs, 1) * 50;
    var positive = val >= 0;

    return React.createElement('div', {
        style: {position: 'relative', width: '100%', height: '100%'}
    }, [
        // The centre line, drawn under the bar. Without it a lone short bar gives the
        // reader nothing to judge its direction against.
        React.createElement('div', {
            key: 'axis',
            style: {position: 'absolute', left: '50%', top: '3px', bottom: '3px',
                    width: '1px', backgroundColor: 'rgba(255,255,255,0.25)'}
        }),
        React.createElement('div', {
            key: 'bar',
            style: {
                position: 'absolute',
                top: '5px', bottom: '5px',
                left: positive ? '50%' : (50 - half) + '%',
                width: half + '%',
                backgroundColor: color,
                borderRadius: '1px'
            }
        })
    ]);
};
