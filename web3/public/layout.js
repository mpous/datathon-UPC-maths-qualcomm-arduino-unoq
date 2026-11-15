/* Injects the shared header and footer so every page has the same shell.
   The brand sits on the left and the navigation on the right of one bar, and
   the router only swaps the middle content, so the header/footer never reload. */
(function () {
  const pages = [
    { key: "home", href: "/", label: "Home", icon: "🏠" },
    { key: "coach", href: "/coach", label: "Coach", icon: "🦘" },
    { key: "solver", href: "/agent", label: "Agent", icon: "🤖" },
    { key: "uploader", href: "/uploader", label: "Uploader", icon: "📤" },
    { key: "analytics", href: "/analytics", label: "Analytics", icon: "📊" },
  ];

  const headerHost = document.getElementById("site-header");
  const footerHost = document.getElementById("site-footer");
  if (!headerHost || !footerHost) return;

  headerHost.innerHTML = `
    <header class="site-header">
      <div class="site-header-inner">
        <a class="brand" href="/" data-nav>
          <span class="brand-title">TIC'S <span>FRIEND</span></span>
          <span class="brand-subtitle" lang="ca">El teu millor amic per les proves cangur!</span>
        </a>
        <nav class="site-nav" aria-label="Main navigation">
          ${pages.map((page) => `
            <a href="${page.href}" data-page="${page.key}" data-nav>
              <span aria-hidden="true">${page.icon}</span><span class="nav-label">${page.label}</span>
            </a>`).join("")}
        </nav>
      </div>
    </header>`;

  footerHost.innerHTML = `
    <footer class="site-footer">
      <div class="site-footer-inner">
        <div class="footer-about">
          <span class="footer-label">About us</span>
          <span class="footer-team">TIC'S FRIENDS</span>
          <ul class="footer-people">
            <li>Marc Bosch Manzano</li>
            <li>Blanca García Rodríguez</li>
            <li>Darcy Thomas Robertson</li>
            <li>Shuangjie Xia</li>
          </ul>
        </div>
        <div class="footer-logos">
          <img class="logo-cell logo-cell-a" src="/logos/upf.jpg" alt="Universitat Pompeu Fabra">
          <img class="logo-cell logo-cell-b" src="/logos/upc.png" alt="Universitat Politècnica de Catalunya">
          <img class="logo-feature" src="/logos/tic-s-friends.jpeg" alt="TIC's Friends">
          <img class="logo-cell logo-cell-c logo-wide" src="/logos/qualcomm-logo.svg" alt="Qualcomm"
               onerror="this.onerror=null;this.src='/logos/qualcomm-logo.png'">
          <img class="logo-cell logo-cell-d logo-square" src="/logos/fme.jpg" alt="Facultat de Matemàtiques i Estadística">
        </div>
      </div>
    </footer>`;

  window.Shell = {
    setActive(key) {
      document.querySelectorAll(".site-nav a").forEach((link) => {
        const active = link.dataset.page === key;
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      });
    },
  };
})();
