/* Tiny client-side router: fetches only the middle fragment of each route and
   swaps it inside #app. The header, the footer and the browser history stay
   alive, so moving between sections never reloads the whole page. */
(function () {
  const routes = {
    "/": {
      key: "home",
      title: "TIC'S FRIEND — Home",
      fragment: "/pages/home.html",
      css: "/pages/home.css",
    },
    "/coach": {
      key: "coach",
      title: "TIC'S FRIEND — Coach",
      fragment: "/pages/coach.html",
      css: "/pages/coach.css",
      js: "/pages/coach.js",
    },
    "/agent": {
      key: "solver",
      title: "TIC'S FRIEND — Agent",
      fragment: "/pages/solver.html",
      css: "/pages/solver.css",
      js: "/pages/solver.js",
    },
    "/uploader": {
      key: "uploader",
      title: "TIC'S FRIEND — Uploader",
      fragment: "/pages/uploader.html",
      css: "/pages/uploader.css",
      js: "/pages/uploader.js",
    },
    "/analytics": {
      key: "analytics",
      title: "TIC'S FRIEND — Analytics",
      fragment: "/pages/analytics.html",
      css: "/pages/analytics.css",
      js: "/pages/analytics.js",
    },
  };

  const aliases = { "/home": "/", "/solver": "/agent", "/teach": "/coach" };

  const app = document.getElementById("app");
  if (!app) return;

  const moduleCache = new Map();
  let cleanup = null;
  let requestId = 0;
  let controller = null;

  function normalize(pathname) {
    const clean = pathname.replace(/\/+$/, "") || "/";
    return aliases[clean] || clean;
  }

  function routeFor(pathname) {
    return routes[normalize(pathname)] || null;
  }

  function loadModule(url) {
    if (!moduleCache.has(url)) {
      const promise = import(url).catch((error) => {
        moduleCache.delete(url);
        throw error;
      });
      moduleCache.set(url, promise);
    }
    return moduleCache.get(url);
  }

  function setPageStyle(css) {
    document.querySelectorAll("style[data-page-css]").forEach((node) => node.remove());
    const style = document.createElement("style");
    style.dataset.pageCss = "";
    style.textContent = css;
    document.head.appendChild(style);
  }

  function showError(error, path) {
    app.innerHTML = `
      <div class="page">
        <section class="panel">
          <h2>This section could not be loaded</h2>
          <p>${String(error.message || error)}</p>
          <p><a class="button" href="${path}">Reload</a></p>
        </section>
      </div>`;
    setPageStyle("");
  }

  async function navigate(path, options = {}) {
    const push = options.push !== false;
    const route = routeFor(path);
    if (!route) {
      window.location.assign(path);
      return;
    }

    const target = normalize(new URL(path, window.location.href).pathname);
    if (push && target === normalize(window.location.pathname) && !window.location.search) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    if (controller) controller.abort();
    controller = new AbortController();
    const id = ++requestId;
    document.body.classList.add("is-navigating");

    try {
      const [html, css] = await Promise.all([
        fetch(route.fragment, { cache: "no-store", signal: controller.signal })
          .then((response) => {
            if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
            return response.text();
          }),
        fetch(route.css, { cache: "no-store", signal: controller.signal })
          .then((response) => (response.ok ? response.text() : "")),
      ]);

      if (id !== requestId) return;

      if (cleanup) {
        try { cleanup(); } catch { /* the old view is already gone */ }
        cleanup = null;
      }

      app.innerHTML = html;
      setPageStyle(css);
      document.title = route.title;
      document.body.dataset.page = route.key;
      if (window.Shell) window.Shell.setActive(route.key);

      if (push) window.history.pushState({ route: route.key }, "", target);
      window.scrollTo({ top: 0, behavior: "auto" });
      app.focus({ preventScroll: true });

      if (route.js) {
        const module = await loadModule(route.js);
        if (id !== requestId) return;
        if (typeof module.mount === "function") cleanup = module.mount(app) || null;
      }
    } catch (error) {
      if (error.name === "AbortError" || id !== requestId) return;
      console.error(error);
      showError(error, target);
    } finally {
      if (id === requestId) document.body.classList.remove("is-navigating");
    }
  }

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const link = event.target.closest("a[href]");
    if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;

    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || !routeFor(url.pathname)) return;

    event.preventDefault();
    navigate(url.pathname + url.search, { push: true });
  });

  window.addEventListener("popstate", () => {
    navigate(window.location.pathname + window.location.search, { push: false });
  });

  const canonical = normalize(window.location.pathname);
  if (canonical !== window.location.pathname) {
    window.history.replaceState({ route: routeFor(canonical)?.key }, "", canonical);
  }
  navigate(window.location.pathname + window.location.search, { push: false });
})();
