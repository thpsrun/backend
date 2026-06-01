(function () {
    "use strict";

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(";").shift();
        return null;
    }

    function getPageLoadedAt() {
        const el = document.getElementById("page_loaded_at");
        return el ? el.value : "";
    }

    function setPageLoadedAt(value) {
        if (!value) return;
        const el = document.getElementById("page_loaded_at");
        if (el) el.value = value;
    }

    document.body.addEventListener("htmx:configRequest", function (evt) {
        const csrf = getCookie("csrftoken");
        if (csrf) evt.detail.headers["X-CSRFToken"] = csrf;
        const loadedAt = getPageLoadedAt();
        if (loadedAt) evt.detail.headers["X-Page-Loaded-At"] = loadedAt;
    });

    function ensureToastStack() {
        let el = document.getElementById("admin-toast-stack");
        if (!el) {
            el = document.createElement("div");
            el.id = "admin-toast-stack";
            document.body.appendChild(el);
        }
        return el;
    }

    function showToast(opts) {
        const stack = ensureToastStack();
        const toast = document.createElement("div");
        toast.className = "adm-toast adm-toast-" + (opts.kind || "info");

        const msg = document.createElement("span");
        msg.className = "adm-toast-message";
        msg.textContent = opts.message || "";
        toast.appendChild(msg);

        if (opts.undo_token && opts.undo_url) {
            const btn = document.createElement("button");
            btn.className = "adm-toast-undo";
            btn.type = "button";
            btn.textContent = "Undo";
            btn.addEventListener("click", function () {
                btn.disabled = true;
                btn.textContent = "Undoing...";
                fetch(opts.undo_url, {
                    method: "POST",
                    headers: { "X-CSRFToken": getCookie("csrftoken") },
                }).then(function (resp) {
                    if (resp.ok) {
                        window.location.reload();
                    } else {
                        btn.disabled = false;
                        btn.textContent = "Undo";
                        showToast({
                            kind: "error",
                            message: "Could not undo - state has changed.",
                        });
                    }
                }).catch(function () {
                    btn.disabled = false;
                    btn.textContent = "Undo";
                    showToast({
                        kind: "error",
                        message: "Network error during undo.",
                    });
                });
            });
            toast.appendChild(btn);
        }

        if (opts.kind === "error" && opts.retry) {
            const btn = document.createElement("button");
            btn.className = "adm-toast-retry";
            btn.type = "button";
            btn.textContent = "Retry";
            btn.addEventListener("click", function () {
                opts.retry();
                toast.remove();
            });
            toast.appendChild(btn);
        }

        const close = document.createElement("button");
        close.className = "adm-toast-close";
        close.type = "button";
        close.textContent = "X";
        close.addEventListener("click", function () { toast.remove(); });
        toast.appendChild(close);

        stack.appendChild(toast);

        const dismissAfter = opts.dismissAfter == null ? 5000 : opts.dismissAfter;
        if (dismissAfter > 0) {
            setTimeout(function () { toast.remove(); }, dismissAfter);
        }
    }

    document.body.addEventListener("adminToast", function (evt) {
        showToast(evt.detail || {});
    });

    document.body.addEventListener("htmx:afterRequest", function (evt) {
        const xhr = evt.detail && evt.detail.xhr;
        if (!xhr) return;
        if (xhr.status >= 200 && xhr.status < 300) {
            setPageLoadedAt(xhr.getResponseHeader("X-New-Page-Loaded-At"));
        }
    });

    function initSortables(root) {
        const scope = root || document;
        scope.querySelectorAll(
            "[data-sortable-scope]:not([data-sortable-bound])",
        ).forEach(function (el) {
            el.dataset.sortableBound = "1";
            const reorderUrl = el.dataset.reorderUrl;
            const sortableScope = el.dataset.sortableScope;
            const groupName = el.dataset.sortableGroup || "scope-" + sortableScope;

            Sortable.create(el, {
                handle: ".adm-grip",
                animation: 150,
                group: groupName,
                onMove: function (evt) {
                    if (evt.from !== evt.to) {
                        evt.dragged.dataset.crossParent = "1";
                    }
                    if (evt.dragged.dataset.searchDisabled === "1") {
                        return false;
                    }
                    return true;
                },
                onEnd: function (evt) {
                    handleSortEnd(evt, sortableScope, reorderUrl, el);
                },
            });
        });
    }

    function handleSortEnd(evt, sortableScope, reorderUrl, list) {
        const finalList = evt.to || list;
        const orderedIds = Array.from(finalList.children).map(function (li) {
            return li.dataset.id;
        });

        const formData = new FormData();
        formData.append("scope", sortableScope);
        orderedIds.forEach(function (id) { formData.append("ordered_ids", id); });

        const extra = finalList.dataset.reorderExtra;
        if (extra) {
            const parsed = JSON.parse(extra);
            Object.keys(parsed).forEach(function (k) {
                formData.append(k, parsed[k]);
            });
        }

        const isCrossParent = evt.item.dataset.crossParent === "1";
        if (isCrossParent) {
            evt.item.dataset.crossParent = "";
            const newParentId = finalList.dataset.parentId || "";
            formData.append("item_id", evt.item.dataset.id);
            formData.append("new_parent_id", newParentId);

            confirmCrossParent(
                evt.item.dataset.name || evt.item.querySelector(".adm-name")?.textContent.trim() || "item",
                evt.from.dataset.parentName || "(root)",
                finalList.dataset.parentName || "(root)",
                function () { postReorder(reorderUrl, formData, finalList, evt); },
                function () { revertDrag(evt); },
            );
            return;
        }

        postReorder(reorderUrl, formData, finalList, evt);
    }

    function postReorder(url, formData, list, evt) {
        fetch(url, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
                "X-Page-Loaded-At": getPageLoadedAt(),
            },
        }).then(function (resp) {
            if (resp.ok) {
                setPageLoadedAt(resp.headers.get("X-New-Page-Loaded-At"));
                refreshOrderNumbers(list);
                resp.text().then(function (html) {
                    const trigger = resp.headers.get("HX-Trigger");
                    if (trigger) tryFireToast(trigger);
                });
            } else if (resp.status === 409) {
                showToast({
                    kind: "error",
                    message: "Page is out of date. Reload to see latest.",
                });
                revertDrag(evt);
            } else {
                showToast({
                    kind: "error",
                    message: "Reorder failed (status " + resp.status + ").",
                    retry: function () { postReorder(url, formData, list, evt); },
                });
                revertDrag(evt);
            }
        }).catch(function () {
            showToast({
                kind: "error",
                message: "Network error.",
                retry: function () { postReorder(url, formData, list, evt); },
            });
            revertDrag(evt);
        });
    }

    function refreshOrderNumbers(list) {
        Array.from(list.children).forEach(function (row, idx) {
            const position = idx + 1;
            const orderSpan = row.querySelector(".adm-order");
            if (orderSpan) {
                orderSpan.textContent = "order: " + position;
            }
            if (row.dataset.unordered === "1") {
                delete row.dataset.unordered;
                const tag = row.querySelector(".adm-unordered-tag");
                if (tag) tag.remove();
            }
        });
    }

    function revertDrag(evt) {
        if (evt.from) {
            const ref = evt.from.children[evt.oldIndex] || null;
            evt.from.insertBefore(evt.item, ref);
        }
    }

    function tryFireToast(headerJson) {
        try {
            const parsed = JSON.parse(headerJson);
            if (parsed && parsed.adminToast) {
                showToast(parsed.adminToast);
            }
        } catch (e) {
        }
    }

    function confirmCrossParent(itemName, fromName, toName, onOk, onCancel) {
        let backdrop = document.querySelector(".adm-modal-backdrop");
        if (!backdrop) {
            backdrop = document.createElement("div");
            backdrop.className = "adm-modal-backdrop";
            backdrop.innerHTML = "<div class='adm-modal'>"
                + "<p class='adm-modal-message'></p>"
                + "<div class='adm-modal-actions'>"
                + "<button type='button' class='adm-modal-cancel'>Cancel</button>"
                + "<button type='button' class='adm-modal-ok default'>Confirm</button>"
                + "</div></div>";
            document.body.appendChild(backdrop);
        }
        backdrop.querySelector(".adm-modal-message").textContent =
            "Move '" + itemName + "' from '" + fromName + "' to '" + toName + "'?";
        backdrop.dataset.open = "1";

        const ok = backdrop.querySelector(".adm-modal-ok");
        const cancel = backdrop.querySelector(".adm-modal-cancel");

        function cleanup() {
            backdrop.dataset.open = "";
            ok.removeEventListener("click", okHandler);
            cancel.removeEventListener("click", cancelHandler);
        }
        function okHandler() { cleanup(); onOk(); }
        function cancelHandler() { cleanup(); onCancel(); }
        ok.addEventListener("click", okHandler);
        cancel.addEventListener("click", cancelHandler);
    }

    function bindSearchInputs(root) {
        const scope = root || document;
        scope.querySelectorAll(
            "[data-search-target]:not([data-search-bound])",
        ).forEach(function (input) {
            input.dataset.searchBound = "1";
            const targetId = input.dataset.searchTarget;
            const list = document.getElementById(targetId);
            if (!list) return;
            let timer = null;
            input.addEventListener("input", function () {
                clearTimeout(timer);
                timer = setTimeout(function () {
                    const q = input.value.trim().toLowerCase();
                    const active = q.length > 0;
                    list.querySelectorAll(".adm-row").forEach(function (row) {
                        const name = (row.dataset.name || "").toLowerCase();
                        row.hidden = active && name.indexOf(q) === -1;
                        row.dataset.searchDisabled = active ? "1" : "";
                    });
                }, 200);
            });
        });
    }

    function bindArrowButtons(root) {
        const scope = root || document;
        scope.querySelectorAll(
            ".adm-arrow:not([data-arrow-bound])",
        ).forEach(function (btn) {
            btn.dataset.arrowBound = "1";
            btn.addEventListener("click", function () {
                const direction = btn.dataset.direction;
                const row = btn.closest(".adm-row");
                if (!row) return;
                const list = row.parentElement;
                if (!list || !list.dataset.sortableScope) return;

                const siblings = Array.from(list.children);
                const idx = siblings.indexOf(row);
                if (direction === "up" && idx <= 0) return;
                if (direction === "down" && idx >= siblings.length - 1) return;

                const newIdx = direction === "up" ? idx - 1 : idx + 1;
                if (newIdx < idx) {
                    list.insertBefore(row, siblings[newIdx]);
                } else {
                    list.insertBefore(row, siblings[newIdx + 1] || null);
                }

                const evt = { item: row, from: list, to: list, oldIndex: idx };
                const reorderUrl = list.dataset.reorderUrl;
                const sortableScope = list.dataset.sortableScope;
                handleSortEnd(evt, sortableScope, reorderUrl, list);
            });
        });
    }

    function bindTreeToggles(root) {
        const scope = root || document;
        scope.querySelectorAll(
            "[data-toggle-children]:not([data-toggle-bound])",
        ).forEach(function (el) {
            el.dataset.toggleBound = "1";
            el.addEventListener("click", function () {
                const row = el.closest(".adm-row");
                if (!row) return;
                const sibling = row.parentElement.querySelector(
                    "li > ul.adm-tree",
                );
                if (!sibling) return;
                const collapsed = sibling.style.display === "none";
                sibling.style.display = collapsed ? "" : "none";
                el.innerHTML = collapsed ? "&#x25BC;" : "&#x25B6;";

                const id = row.dataset.id;
                if (id) {
                    const key = "adm-nav-collapsed";
                    const stored = JSON.parse(localStorage.getItem(key) || "{}");
                    if (collapsed) {
                        delete stored[id];
                    } else {
                        stored[id] = 1;
                    }
                    localStorage.setItem(key, JSON.stringify(stored));
                }
            });
        });

        const stored = JSON.parse(
            localStorage.getItem("adm-nav-collapsed") || "{}",
        );
        Object.keys(stored).forEach(function (id) {
            const row = scope.querySelector(
                ".adm-row[data-id=\"" + CSS.escape(id) + "\"]",
            );
            if (!row) return;
            const sibling = row.parentElement.querySelector(
                "li > ul.adm-tree",
            );
            if (sibling) sibling.style.display = "none";
            const toggle = row.querySelector("[data-toggle-children]");
            if (toggle) toggle.innerHTML = "&#x25B6;";
        });
    }

    function initAll(root) {
        initSortables(root);
        bindSearchInputs(root);
        bindArrowButtons(root);
        bindTreeToggles(root);
    }

    document.addEventListener("DOMContentLoaded", function () { initAll(); });
    document.body.addEventListener("htmx:afterSwap", function (evt) {
        initAll(evt.target);
    });

    window.adminCustom = window.adminCustom || {};
    window.adminCustom.showToast = showToast;
    window.adminCustom.getCookie = getCookie;
    window.adminCustom.initAll = initAll;
})();
