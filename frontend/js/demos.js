/**
 * TraceHeal Multi-Storefront Interactive Demo Engine
 * Three authentic, distinct e-commerce/delivery workloads connected to the TraceHeal SRE mesh:
 * 1. BiteRush (Food Delivery) -> payment-service (DB_POOL_EXHAUSTION)
 * 2. ApexMart (E-Commerce) -> inventory-service / gateway (LATENCY_SPIKE)
 * 3. FlashDrop (Quick Commerce) -> payment-service (DEADLOCK)
 */

(function () {
  "use strict";

  // Self-contained safe string escaper
  function safeEscape(str) {
    if (typeof str !== "string") return str == null ? "" : String(str);
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  const DemoStoreEngine = {
    // Active demo view: "hub", "food", "ecommerce", "quickcommerce"
    currentStore: "hub",

    // Store Carts
    carts: {
      food: [
        { id: "f1", name: "Margherita Supreme", price: 14.99, qty: 1, restaurant: "The Pizza Matrix", img: "🍕" },
        { id: "f2", name: "Loaded Truffle Fries", price: 5.99, qty: 1, restaurant: "CyberBurger Lab", img: "🍟" }
      ],
      ecommerce: [
        { id: "e1", name: "AeroTune Pro ANC Headphones", price: 249.99, qty: 1, brand: "AeroAcoustics", img: "🎧" }
      ],
      quickcommerce: [
        { id: "q1", name: "OatHaven Barista Oat Milk (1L)", price: 4.49, qty: 2, cat: "Dairy", img: "🥛" },
        { id: "q2", name: "Organic Hass Avocados (4-Pack)", price: 5.99, qty: 1, cat: "Produce", img: "🥑" }
      ]
    },

    // Chaos state per storefront
    chaosArmed: {
      food: false,
      ecommerce: false,
      quickcommerce: false
    },

    // Active failure context
    activeIncidentContext: null,

    // Catalogs
    catalog: {
      food: {
        name: "BiteRush Express",
        tagline: "Instant Craving Delivery Mesh",
        accent: "#F97316",
        targetService: "payment-service",
        faultType: "DB_POOL_EXHAUSTION",
        deliveryFee: 2.99,
        restaurants: [
          {
            id: "r1",
            name: "The Pizza Matrix",
            rating: "4.9 ★",
            eta: "20-30 min",
            items: [
              { id: "f1", name: "Margherita Supreme", desc: "San Marzano tomatoes, fresh buffalo mozzarella, basil, EVOO", price: 14.99, img: "🍕" },
              { id: "f3", name: "Truffle Mushroom Feast", desc: "Wild forest mushrooms, black truffle glaze, fontina cheese", price: 18.50, img: "🍄" },
              { id: "f4", name: "Garlic Herb Knots", desc: "Hand-rolled sourdough, roasted garlic butter, parsley", price: 6.99, img: "🥖" }
            ]
          },
          {
            id: "r2",
            name: "CyberBurger Lab",
            rating: "4.8 ★",
            eta: "15-25 min",
            items: [
              { id: "f5", name: "Quantum Double Smash", desc: "Two smashed Angus patties, secret umami sauce, brioche", price: 13.49, img: "🍔" },
              { id: "f6", name: "Crispy Avocado Chicken", desc: "Free-range breast, spicy remoulade, house pickles", price: 12.99, img: "🍗" },
              { id: "f2", name: "Loaded Truffle Fries", desc: "Parmigiano-Reggiano, truffle oil, smoked sea salt", price: 5.99, img: "🍟" }
            ]
          },
          {
            id: "r3",
            name: "Tokyo Noodle Hub",
            rating: "4.95 ★",
            eta: "25-35 min",
            items: [
              { id: "f7", name: "Tonkotsu Chashu Ramen", desc: "24-hr pork bone broth, tender chashu, ajitsuke tamago", price: 16.00, img: "🍜" },
              { id: "f8", name: "Spicy Miso Tantanmen", desc: "Rich sesame miso, spicy minced pork, scallions", price: 15.50, img: "🍲" },
              { id: "f9", name: "Pan-Seared Gyoza (6pc)", desc: "Kurobuta pork, crisp lace crust, chili ponzu", price: 7.50, img: "🥟" }
            ]
          }
        ]
      },

      ecommerce: {
        name: "ApexMart",
        tagline: "Global Electronics & Lifestyle Mesh",
        accent: "#6366F1",
        targetService: "inventory-service",
        faultType: "LATENCY_SPIKE",
        shippingFee: 0.00, // Free shipping
        products: [
          { id: "e1", name: "AeroTune Pro ANC Headphones", desc: "Hybrid Active Noise Cancellation with 40-hr battery & lossless audio", price: 249.99, inStock: 14, rating: "4.9 ★", img: "🎧", badge: "BESTSELLER" },
          { id: "e2", name: "Vortex 34\" Curved 4K Display", desc: "144Hz Nano-IPS panel, 98% DCI-P3, USB-C 90W PD charging", price: 599.00, inStock: 6, rating: "4.8 ★", img: "🖥️", badge: "PRO CHOICE" },
          { id: "e3", name: "KeyForge RGB Mechanical Keeb", desc: "Hot-swappable linear switches, aircraft aluminum chassis, PBT caps", price: 129.99, inStock: 22, rating: "4.9 ★", img: "⌨️", badge: "POPULAR" },
          { id: "e4", name: "ErgoGlide Precision Wireless Mouse", desc: "4K polling rate, 26,000 DPI sensor, ergonomic contour grip", price: 79.50, inStock: 18, rating: "4.7 ★", img: "🖱️", badge: "TOP RATED" },
          { id: "e5", name: "MagPulse 3-in-1 Fast Charger", desc: "15W MagSafe, Apple Watch fast charging, Qi earbuds tray", price: 49.99, inStock: 35, rating: "4.8 ★", img: "⚡", badge: "NEW" },
          { id: "e6", name: "TitanFlow Aluminum Laptop Stand", desc: "Dual-hinge adjustable height with passive cooling ventilation", price: 39.99, inStock: 42, rating: "4.9 ★", img: "💻", badge: "FEATURED" }
        ]
      },

      quickcommerce: {
        name: "FlashDrop 10-Min",
        tagline: "Ultra-Fast Dark Store Fulfillment",
        accent: "#10B981",
        targetService: "payment-service",
        faultType: "DEADLOCK",
        dispatchFee: 1.49,
        eta: "8-12 min",
        items: [
          { id: "q1", name: "OatHaven Barista Oat Milk (1L)", cat: "Dairy & Plant Milk", price: 4.49, stock: 24, img: "🥛" },
          { id: "q2", name: "Organic Hass Avocados (4-Pack)", cat: "Fresh Produce", price: 5.99, stock: 18, img: "🥑" },
          { id: "q3", name: "Artisan Sourdough Loaf (750g)", cat: "Bakery", price: 6.49, stock: 12, img: "🍞" },
          { id: "q4", name: "Nitro Cold Brew Coffee Can", cat: "Beverages", price: 3.99, stock: 40, img: "☕" },
          { id: "q5", name: "Ceremonial Japanese Matcha (30g)", cat: "Tea & Wellness", price: 18.99, stock: 9, img: "🍵" },
          { id: "q6", name: "Roasted Rosemary Sea Salt Almonds", cat: "Snacks", price: 7.29, stock: 30, img: "🥜" }
        ]
      }
    },

    init() {
      try {
        this.renderFoodStore();
        this.renderEcommerceStore();
        this.renderQuickCommerceStore();
        this.updateCartUI("food");
        this.updateCartUI("ecommerce");
        this.updateCartUI("quickcommerce");
      } catch (err) {
        console.warn("DemoStoreEngine init error:", err);
      }
    },

    // Navigation Methods
    openStore(storeKey) {
      this.currentStore = storeKey;
      if (typeof window.switchMainView === "function") {
        window.switchMainView("storefront");
      }
      document.querySelectorAll(".store-container").forEach((el) => {
        el.style.display = el.id === `store-${storeKey}` ? "block" : "none";
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    },

    openHub() {
      this.currentStore = "hub";
      if (typeof window.switchMainView === "function") {
        window.switchMainView("demohub");
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    },

    // Store Renderers
    renderFoodStore() {
      const container = document.getElementById("foodRestaurantsList");
      if (!container) return;
      const data = this.catalog.food;
      let html = "";

      data.restaurants.forEach((r) => {
        html += `
          <div class="store-restaurant-card">
            <div class="store-rest-header">
              <div>
                <h3 class="store-rest-title">${safeEscape(r.name)}</h3>
                <div class="store-rest-meta">
                  <span class="rest-rating">${safeEscape(r.rating)}</span>
                  <span class="rest-sep">•</span>
                  <span class="rest-eta">⚡ ${safeEscape(r.eta)}</span>
                </div>
              </div>
              <span class="badge-store-tag">Mesh Node: order-service:8081</span>
            </div>
            <div class="store-items-grid">
              ${r.items
                .map(
                  (item) => `
                <div class="store-item-card">
                  <div class="store-item-top">
                    <span class="store-item-emoji">${item.img}</span>
                    <div class="store-item-price">$${item.price.toFixed(2)}</div>
                  </div>
                  <div class="store-item-name">${safeEscape(item.name)}</div>
                  <div class="store-item-desc">${safeEscape(item.desc)}</div>
                  <button class="btn-add-cart" onclick="DemoStoreEngine.addToCart('food', '${item.id}')">
                    + Add to Cart
                  </button>
                </div>
              `
                )
                .join("")}
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
    },

    renderEcommerceStore() {
      const container = document.getElementById("ecommerceProductsGrid");
      if (!container) return;
      const data = this.catalog.ecommerce;
      let html = "";

      data.products.forEach((p) => {
        html += `
          <div class="store-product-card">
            <div class="product-badge-row">
              <span class="product-pill-badge">${safeEscape(p.badge)}</span>
              <span class="stock-indicator">In Stock (${p.inStock})</span>
            </div>
            <div class="product-visual-box">
              <span class="product-emoji">${p.img}</span>
            </div>
            <div class="product-details">
              <div class="product-rating">${safeEscape(p.rating)} (Verified SRE Buyers)</div>
              <h3 class="product-title">${safeEscape(p.name)}</h3>
              <p class="product-desc">${safeEscape(p.desc)}</p>
              <div class="product-footer-row">
                <div class="product-price">$${p.price.toFixed(2)}</div>
                <button class="btn-add-cart" onclick="DemoStoreEngine.addToCart('ecommerce', '${p.id}')">
                  Add to Cart
                </button>
              </div>
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
    },

    renderQuickCommerceStore() {
      const container = document.getElementById("quickCommerceGrid");
      if (!container) return;
      const data = this.catalog.quickcommerce;
      let html = "";

      data.items.forEach((item) => {
        html += `
          <div class="qcom-item-card">
            <div class="qcom-item-visual">
              <span class="qcom-emoji">${item.img}</span>
              <span class="qcom-eta-badge">⚡ 10m delivery</span>
            </div>
            <div class="qcom-category">${safeEscape(item.cat)}</div>
            <div class="qcom-name">${safeEscape(item.name)}</div>
            <div class="qcom-bottom">
              <div class="qcom-price">$${item.price.toFixed(2)}</div>
              <button class="btn-qcom-add" onclick="DemoStoreEngine.addToCart('quickcommerce', '${item.id}')">
                + Add
              </button>
            </div>
          </div>
        `;
      });
      container.innerHTML = html;
    },

    // Cart Management
    addToCart(storeKey, itemId) {
      const store = this.catalog[storeKey];
      let item = null;

      if (storeKey === "food") {
        for (const r of store.restaurants) {
          const match = r.items.find((i) => i.id === itemId);
          if (match) {
            item = { ...match, restaurant: r.name };
            break;
          }
        }
      } else if (storeKey === "ecommerce") {
        item = store.products.find((i) => i.id === itemId);
      } else if (storeKey === "quickcommerce") {
        item = store.items.find((i) => i.id === itemId);
      }

      if (!item) return;

      const cart = this.carts[storeKey];
      const existing = cart.find((i) => i.id === itemId);
      if (existing) {
        existing.qty += 1;
      } else {
        cart.push({ ...item, qty: 1 });
      }

      this.updateCartUI(storeKey);
      if (typeof window.showToast === "function") {
        window.showToast("Added to Cart", `${item.name} added to your ${store.name} cart.`, "info");
      }
    },

    updateQuantity(storeKey, itemId, delta) {
      const cart = this.carts[storeKey];
      const item = cart.find((i) => i.id === itemId);
      if (!item) return;

      item.qty += delta;
      if (item.qty <= 0) {
        this.carts[storeKey] = cart.filter((i) => i.id !== itemId);
      }

      this.updateCartUI(storeKey);
    },

    removeFromCart(storeKey, itemId) {
      this.carts[storeKey] = this.carts[storeKey].filter((i) => i.id !== itemId);
      this.updateCartUI(storeKey);
    },

    updateCartUI(storeKey) {
      const cart = this.carts[storeKey] || [];
      const countEl = document.getElementById(`${storeKey}CartCount`);
      const itemsEl = document.getElementById(`${storeKey}CartItems`);
      const subtotalEl = document.getElementById(`${storeKey}CartSubtotal`);
      const totalEl = document.getElementById(`${storeKey}CartTotal`);
      const btnCheckout = document.getElementById(`${storeKey}BtnCheckout`);

      const totalItems = cart.reduce((sum, i) => sum + i.qty, 0);
      const subtotal = cart.reduce((sum, i) => sum + i.price * i.qty, 0);

      let extraFee = 0;
      let tax = subtotal * 0.08;
      if (storeKey === "food") extraFee = 2.99;
      if (storeKey === "quickcommerce") extraFee = 1.49;
      const grandTotal = subtotal > 0 ? subtotal + extraFee + tax : 0;

      if (countEl) countEl.textContent = `${totalItems} ${totalItems === 1 ? "item" : "items"}`;
      if (subtotalEl) subtotalEl.textContent = `$${subtotal.toFixed(2)}`;
      if (totalEl) totalEl.textContent = `$${grandTotal.toFixed(2)}`;

      if (btnCheckout) {
        btnCheckout.disabled = cart.length === 0;
      }

      if (itemsEl) {
        if (cart.length === 0) {
          itemsEl.innerHTML = `
            <div class="cart-empty-state">
              <span class="empty-cart-icon">🛒</span>
              <p>Your cart is empty.</p>
              <span class="empty-hint">Add items from the catalog above to test simulated checkout.</span>
            </div>
          `;
        } else {
          itemsEl.innerHTML = cart
            .map(
              (i) => `
            <div class="cart-item-row">
              <div class="cart-row-left">
                <span class="cart-row-emoji">${i.img || "📦"}</span>
                <div>
                  <div class="cart-row-name">${safeEscape(i.name)}</div>
                  <div class="cart-row-price">$${i.price.toFixed(2)} each</div>
                </div>
              </div>
              <div class="cart-row-controls">
                <button class="cart-qty-btn" onclick="DemoStoreEngine.updateQuantity('${storeKey}', '${i.id}', -1)">−</button>
                <span class="cart-qty-val">${i.qty}</span>
                <button class="cart-qty-btn" onclick="DemoStoreEngine.updateQuantity('${storeKey}', '${i.id}', 1)">+</button>
                <button class="cart-remove-btn" title="Remove" onclick="DemoStoreEngine.removeFromCart('${storeKey}', '${i.id}')">✕</button>
              </div>
            </div>
          `
            )
            .join("");
        }
      }
    },

    // Chaos Arming Toggle
    toggleStoreChaos(storeKey) {
      this.chaosArmed[storeKey] = !this.chaosArmed[storeKey];
      const isArmed = this.chaosArmed[storeKey];
      this.updateChaosButtonUI(storeKey);

      if (typeof window.showToast === "function") {
        if (isArmed) {
          window.showToast("Chaos Armed", `Simulated fault (${this.catalog[storeKey].faultType}) armed on ${this.catalog[storeKey].targetService}. Click checkout to trigger failure.`, "warning");
        } else {
          window.showToast("Chaos Disarmed", "Storefront returned to nominal operation.", "info");
        }
      }
    },

    updateChaosButtonUI(storeKey) {
      const isArmed = this.chaosArmed[storeKey];
      const btn = document.getElementById(`${storeKey}ChaosToggleBtn`);
      const statusPill = document.getElementById(`${storeKey}MeshStatusPill`);

      if (btn) {
        if (isArmed) {
          btn.classList.add("armed");
          btn.innerHTML = `⚠️ Chaos Armed: ${this.catalog[storeKey].faultType}`;
        } else {
          btn.classList.remove("armed");
          btn.innerHTML = `⚡ Arm Anomaly (${this.catalog[storeKey].faultType})`;
        }
      }

      if (statusPill) {
        if (isArmed) {
          statusPill.className = "mesh-pill degraded";
          statusPill.textContent = "CHAOS SIMULATION ACTIVE";
        } else {
          statusPill.className = "mesh-pill nominal";
          statusPill.textContent = "ALL NODES NOMINAL";
        }
      }
    },

    // Checkout Execution
    async executeCheckout(storeKey) {
      const items = this.carts[storeKey] || [];
      if (items.length === 0) {
        if (typeof window.showToast === "function") {
          window.showToast("Cart Empty", "Please add at least one item to proceed with checkout.", "warning");
        }
        return;
      }

      const store = this.catalog[storeKey];
      const isArmed = this.chaosArmed[storeKey];
      const btnCheckout = document.getElementById(`${storeKey}BtnCheckout`);

      if (btnCheckout) {
        btnCheckout.disabled = true;
        btnCheckout.innerHTML = `<span class="spinner-inline"></span> Processing Distributed Order...`;
      }

      // Short realistic network delay
      await new Promise((r) => setTimeout(r, 650));

      if (isArmed) {
        // Trigger genuine incident on backend via /api/v1/chaos/simulate-incident
        try {
          const resp = await fetch("/api/v1/chaos/simulate-incident", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              fault_type: store.faultType,
              target_service: store.targetService,
              trace_count: 3,
              force_new: true,
            }),
          });

          const data = await resp.json();
          const inc = data.incident;

          this.activeIncidentContext = {
            storeKey: storeKey,
            storeName: store.name,
            incidentId: inc ? inc.id : "SIM-" + Date.now().toString(16),
            faultType: store.faultType,
            targetService: store.targetService,
            title: inc ? inc.title : `${store.faultType} on ${store.targetService}`,
          };

          // Render failure banner on storefront
          this.showCheckoutFailureBanner(storeKey, this.activeIncidentContext);

          if (typeof window.triggerWarRoomAlert === "function") {
            window.triggerWarRoomAlert({ service: store.targetService, scenario: store.faultType });
          }
          if (typeof window.showToast === "function") {
            window.showToast("Checkout Failed (HTTP 500)", `Downstream failure in ${store.targetService}. Incident flagged in TraceHeal!`, "error");
          }
        } catch (err) {
          console.error("Simulation error:", err);
        } finally {
          if (btnCheckout) {
            btnCheckout.disabled = false;
            btnCheckout.innerHTML = `Retry Checkout`;
          }
        }
      } else {
        // Normal successful checkout
        if (btnCheckout) {
          btnCheckout.disabled = false;
          btnCheckout.innerHTML = `Place Order`;
        }
        this.showCheckoutSuccessModal(storeKey);
        this.carts[storeKey] = [];
        this.updateCartUI(storeKey);
      }
    },

    showCheckoutFailureBanner(storeKey, context) {
      const banner = document.getElementById(`${storeKey}FailureAlert`);
      if (!banner) return;

      banner.style.display = "block";
      banner.innerHTML = `
        <div class="store-alert-inner">
          <div class="store-alert-left">
            <span class="store-alert-badge">P1 CRITICAL FAILURE</span>
            <div>
              <strong>Transaction Aborted: 500 Internal Server Error in ${safeEscape(context.targetService)}</strong>
              <p>Cascading fault detected during W3C trace propagation. TraceHeal autonomous observer has correlated root-cause hypotheses.</p>
            </div>
          </div>
          <div class="store-alert-actions">
            <button class="btn btn-hero btn-sm" onclick="DemoStoreEngine.investigateInTraceHeal()">
              🔍 Investigate in TraceHeal →
            </button>
            <button class="btn btn-secondary btn-sm" onclick="DemoStoreEngine.autoHealFromStore('${storeKey}')">
              ⚡ 1-Click Auto-Heal
            </button>
          </div>
        </div>
      `;
      banner.scrollIntoView({ behavior: "smooth", block: "center" });
    },

    showCheckoutSuccessModal(storeKey) {
      const store = this.catalog[storeKey];
      const orderNum = "ORD-" + Math.floor(100000 + Math.random() * 900000);
      const modal = document.getElementById("storeOrderSuccessModal");
      const content = document.getElementById("storeOrderSuccessContent");
      if (!modal || !content) return;

      content.innerHTML = `
        <div class="success-graphic">✓</div>
        <h3 style="font-size: 20px; font-weight: 700; color: #FFFFFF; margin-bottom: 8px;">Order Confirmed!</h3>
        <p class="order-id" style="font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #06B6D4; margin-bottom: 8px;">Order Reference: <code>${orderNum}</code></p>
        <p class="order-desc" style="font-size: 13px; color: #94A3B8; line-height: 1.6; margin-bottom: 24px;">Thank you for ordering with <strong>${safeEscape(store.name)}</strong>. All microservices in the distributed checkout mesh (${safeEscape(store.targetService)}) processed within SLO (&lt; 25ms).</p>
        <div class="success-actions" style="display: flex; gap: 10px; justify-content: center;">
          <button class="btn btn-primary" onclick="DemoStoreEngine.closeOrderModal()">Continue Exploring</button>
          <button class="btn btn-secondary" onclick="DemoStoreEngine.openHub()">Try Another Demo App</button>
        </div>
      `;
      modal.classList.add("active");
      modal.classList.add("open");
    },

    closeOrderModal() {
      const modal = document.getElementById("storeOrderSuccessModal");
      if (modal) {
        modal.classList.remove("active");
        modal.classList.remove("open");
      }
    },

    // Transition to TraceHeal with Active Context
    investigateInTraceHeal() {
      if (typeof window.navigateTo === "function") {
        window.navigateTo("investigation");
      } else if (typeof window.switchMainView === "function") {
        window.switchMainView("commandcenter");
      }

      const ctx = this.activeIncidentContext;
      if (ctx) {
        this.updateInvestigationContextBanner(ctx);
        if (typeof window.loadIncidents === "function") {
          window.loadIncidents().then(() => {
            if (ctx.incidentId && typeof window.selectAndInvestigate === "function") {
              window.selectAndInvestigate(ctx.incidentId);
            }
          });
        }
      }
    },

    async autoHealFromStore(storeKey) {
      if (typeof window.showToast === "function") {
        window.showToast("Auto-Healing Active Anomaly", "Triggering 7-stage closed-loop remediation...", "info");
      }
      this.investigateInTraceHeal();
      if (typeof window.runAutoHealCycle === "function") {
        await window.runAutoHealCycle();
      }
    },

    updateInvestigationContextBanner(ctx) {
      const banner = document.getElementById("storefrontInvestigationBanner");
      if (!banner) return;

      banner.style.display = "flex";
      banner.className = "investigation-context-banner";
      banner.innerHTML = `
        <div class="investigation-meta">
          <span class="inv-badge">ACTIVE DEMO CONTEXT</span>
          <span class="inv-store" style="font-weight: 600; color: #F8FAFC;">${safeEscape(ctx.storeName)}</span>
          <span class="inv-sep" style="color: #64748B;">/</span>
          <span class="inv-service" style="color: #38BDF8; font-family: monospace;">${safeEscape(ctx.targetService)}</span>
          <span class="inv-fault" style="color: #F59E0B; font-size: 11px;">(${safeEscape(ctx.faultType)})</span>
        </div>
        <div class="investigation-actions">
          <button class="btn btn-secondary btn-xs" onclick="DemoStoreEngine.returnToActiveStore()">
            ← Return to ${safeEscape(ctx.storeName)} Storefront
          </button>
        </div>
      `;
    },

    returnToActiveStore() {
      if (this.activeIncidentContext) {
        this.openStore(this.activeIncidentContext.storeKey);
      } else {
        this.openStore("food");
      }
    },

    markIncidentHealed() {
      const banner = document.getElementById("storefrontInvestigationBanner");
      if (banner && this.activeIncidentContext) {
        banner.className = "investigation-context-banner healed";
        banner.innerHTML = `
          <div class="investigation-meta">
            <span class="inv-badge success">✓ RESOLVED & VERIFIED</span>
            <span style="font-size: 12px; color: #E2E8F0;">Zero-regression hotfix verified in sandbox for <strong>${safeEscape(this.activeIncidentContext.targetService)}</strong>.</span>
          </div>
          <div class="investigation-actions">
            <button class="btn btn-hero btn-xs" onclick="DemoStoreEngine.returnAndRetryCheckout()">
              ← Return to ${safeEscape(this.activeIncidentContext.storeName)} & Retry Checkout
            </button>
          </div>
        `;
      }
    },

    returnAndRetryCheckout() {
      if (!this.activeIncidentContext) {
        this.openHub();
        return;
      }
      const storeKey = this.activeIncidentContext.storeKey;
      // Disarm chaos so retry succeeds
      this.chaosArmed[storeKey] = false;
      this.updateChaosButtonUI(storeKey);
      const failureBanner = document.getElementById(`${storeKey}FailureAlert`);
      if (failureBanner) failureBanner.style.display = "none";
      this.openStore(storeKey);
      if (typeof window.showToast === "function") {
        window.showToast("Mesh Restored", "Cluster nominal. You can now retry checkout successfully!", "success");
      }
    }
  };

  // Expose to window immediately
  window.DemoStoreEngine = DemoStoreEngine;
})();
