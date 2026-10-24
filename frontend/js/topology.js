/**
 * TraceHeal SVG Service Topology & Dynamic Auto-Discovery Component
 * 
 * World-Class Interactive Microservice Mesh Architecture:
 * - Dynamic Service Auto-Discovery from OpenTelemetry distributed traces
 * - Live animated cyber-traffic packet flow along bezier curves
 * - High-tech glowing node cards with status rings, service icons, and metrics
 * - Interactive node selection, pinging, chaos testing, and auto-layout
 */

class TopologyRenderer {
  constructor(containerId = "topologyCanvas") {
    this.containerId = containerId;
    this.container = document.getElementById(containerId);
    
    // Default 6-tier microservice cluster positions (820x480 coordinate space)
    this.nodes = {
      "gateway-service": { x: 120, y: 200, label: "gateway-service", port: 8080, status: "HEALTHY", latency: 8, errorRate: 0, depth: 0, icon: "🌐", role: "Ingress Gateway" },
      "auth-service": { x: 120, y: 360, label: "auth-service", port: 8084, status: "HEALTHY", latency: 4, errorRate: 0, depth: 0, icon: "🔒", role: "Auth / Tokens" },
      "order-service": { x: 380, y: 200, label: "order-service", port: 8081, status: "HEALTHY", latency: 15, errorRate: 0, depth: 1, icon: "🛒", role: "Core Orchestrator" },
      "payment-service": { x: 670, y: 110, label: "payment-service", port: 8082, status: "HEALTHY", latency: 22, errorRate: 0, depth: 2, icon: "💳", role: "Payments & Pool" },
      "inventory-service": { x: 670, y: 240, label: "inventory-service", port: 8083, status: "HEALTHY", latency: 14, errorRate: 0, depth: 2, icon: "📦", role: "Warehouse & Stock" },
      "notification-service": { x: 670, y: 370, label: "notification-service", port: 8085, status: "HEALTHY", latency: 9, errorRate: 0, depth: 2, icon: "🔔", role: "Async Dispatcher" },
    };

    this.edges = [
      { from: "gateway-service", to: "auth-service", label: "4ms", status: "normal" },
      { from: "gateway-service", to: "order-service", label: "15ms", status: "normal" },
      { from: "order-service", to: "payment-service", label: "22ms", status: "normal" },
      { from: "order-service", to: "inventory-service", label: "14ms", status: "normal" },
      { from: "order-service", to: "notification-service", label: "9ms", status: "normal" },
    ];

    this.selectedNode = "payment-service";
    this.render();
  }

  /**
   * Auto-discovers arbitrary nodes and dynamically positions them using depth/rank layout.
   */
  autoDiscoverNode(serviceName, port = null, parentService = null, latency = 20, errorRate = 0) {
    if (!serviceName) return;

    if (!this.nodes[serviceName]) {
      const parentDepth = parentService && this.nodes[parentService] ? this.nodes[parentService].depth : 0;
      const depth = parentService ? parentDepth + 1 : 1;

      // Calculate position based on depth column and count in this column
      const colX = Math.min(680, 120 + depth * 250);
      const existingInCol = Object.values(this.nodes).filter(n => Math.abs(n.x - colX) < 50).length;
      const posY = 120 + (existingInCol * 130);

      this.nodes[serviceName] = {
        x: colX,
        y: posY,
        label: serviceName,
        port: port || (8000 + Object.keys(this.nodes).length),
        status: errorRate > 0 ? "UNHEALTHY" : "HEALTHY",
        latency: latency,
        errorRate: errorRate,
        depth: depth,
        dynamic: true,
        icon: "⚡",
        role: "Discovered Service"
      };

      if (parentService && this.nodes[parentService]) {
        const edgeExists = this.edges.some(e => e.from === parentService && e.to === serviceName);
        if (!edgeExists) {
          this.edges.push({
            from: parentService,
            to: serviceName,
            label: `${latency}ms`,
            status: errorRate > 0 ? "error" : "normal",
          });
        }
      }

      this.rebalanceLayout();
      this.render();
    } else {
      if (latency !== null) this.nodes[serviceName].latency = latency;
      if (errorRate !== null) {
        this.nodes[serviceName].errorRate = errorRate;
        this.nodes[serviceName].status = errorRate > 0 ? "UNHEALTHY" : "HEALTHY";
      }
    }
  }

  /**
   * Automatically ingests distributed spans and reconstructs the complete service graph.
   */
  updateFromTraceSpans(spans) {
    if (!Array.isArray(spans) || spans.length === 0) return;

    const spanMap = new Map();
    spans.forEach(s => spanMap.set(s.span_id, s));

    spans.forEach(s => {
      let parentService = null;
      if (s.parent_span_id && spanMap.has(s.parent_span_id)) {
        parentService = spanMap.get(s.parent_span_id).service_name;
      }

      const isErr = s.status_code === "ERROR" || (s.http_status_code && s.http_status_code >= 500);
      this.autoDiscoverNode(
        s.service_name,
        null,
        parentService !== s.service_name ? parentService : null,
        Math.round(s.duration_ms || 15),
        isErr ? 1.0 : 0.0
      );
    });

    this.render();
  }

  rebalanceLayout() {
    const cols = {};
    Object.entries(this.nodes).forEach(([key, n]) => {
      const colKey = Math.round(n.x / 200);
      if (!cols[colKey]) cols[colKey] = [];
      cols[colKey].push(n);
    });

    Object.values(cols).forEach(colNodes => {
      const step = 420 / (colNodes.length + 1);
      colNodes.forEach((node, i) => {
        node.y = Math.round(step * (i + 1) + 40);
      });
    });
  }

  render() {
    if (!this.container) {
      this.container = document.getElementById(this.containerId);
    }
    if (!this.container) return;

    const width = 840;
    const height = 480;

    let svg = `
      <svg class="topology-svg" width="100%" height="100%" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <!-- Cyber Ambient Grid Pattern -->
          <pattern id="cyberGrid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(56, 189, 248, 0.04)" stroke-width="1" />
            <circle cx="0" cy="0" r="1.2" fill="rgba(56, 189, 248, 0.15)" />
          </pattern>

          <!-- Glow Filters -->
          <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="glow-red" x="-25%" y="-25%" width="150%" height="150%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="glow-amber" x="-25%" y="-25%" width="150%" height="150%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <!-- Node Gradients -->
          <linearGradient id="nodeGradHealthy" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#141E33" />
            <stop offset="100%" stop-color="#0E1627" />
          </linearGradient>
          <linearGradient id="nodeGradCritical" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#2E1318" />
            <stop offset="100%" stop-color="#180A0D" />
          </linearGradient>
          <linearGradient id="nodeGradSelected" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#1A2844" />
            <stop offset="100%" stop-color="#0F1B30" />
          </linearGradient>

          <!-- Directed Link Arrow Markers -->
          <marker id="arrow-cyan" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#38BDF8" />
          </marker>
          <marker id="arrow-red" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#EF4444" />
          </marker>
          <marker id="arrow-amber" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#F59E0B" />
          </marker>
        </defs>

        <!-- Grid Background Plane -->
        <rect width="${width}" height="${height}" fill="url(#cyberGrid)" />

        <!-- Subtitle & Layer Guides -->
        <g opacity="0.4" font-family="JetBrains Mono, monospace" font-size="10" fill="#64748B">
          <text x="120" y="32" text-anchor="middle">INGRESS TIER</text>
          <text x="380" y="32" text-anchor="middle">ORCHESTRATION</text>
          <text x="670" y="32" text-anchor="middle">DOWNSTREAM MESH</text>
          <line x1="250" y1="20" x2="250" y2="${height - 20}" stroke="rgba(255,255,255,0.04)" stroke-dasharray="3 3" />
          <line x1="525" y1="20" x2="525" y2="${height - 20}" stroke="rgba(255,255,255,0.04)" stroke-dasharray="3 3" />
        </g>

        <!-- Edges (Connections & Animated Traffic Packets) -->
        <g class="edges-group">
    `;

    this.edges.forEach((edge, idx) => {
      const src = this.nodes[edge.from];
      const dst = this.nodes[edge.to];
      if (!src || !dst) return;

      const isError = edge.status === "error";
      const isDegraded = edge.status === "degraded";
      const edgeClass = isError ? "edge-path error" : isDegraded ? "edge-path degraded" : "edge-path active";
      const marker = isError ? "url(#arrow-red)" : isDegraded ? "url(#arrow-amber)" : "url(#arrow-cyan)";
      const particleColor = isError ? "#EF4444" : isDegraded ? "#F59E0B" : "#00F0FF";

      // Curved bezier path
      const midX = (src.x + dst.x) / 2;
      const midY = (src.y + dst.y) / 2;
      const pathId = `edge-track-${idx}`;
      const pathD = `M ${src.x} ${src.y} Q ${midX} ${src.y} ${dst.x} ${dst.y}`;

      svg += `
        <!-- Edge Track Line -->
        <path id="${pathId}" d="${pathD}" class="${edgeClass}" marker-end="${marker}" />

        <!-- Real-Time Flowing Traffic Packet -->
        <circle r="${isError ? 4.5 : 3.5}" fill="${particleColor}" class="traffic-particle ${isError ? 'error' : ''}">
          <animateMotion dur="${isError ? '1.5s' : '2.8s'}" repeatCount="indefinite" path="${pathD}" />
        </circle>
        <circle r="2" fill="${particleColor}" opacity="0.6">
          <animateMotion dur="${isError ? '1.5s' : '2.8s'}" begin="${isError ? '0.75s' : '1.4s'}" repeatCount="indefinite" path="${pathD}" />
        </circle>

        <!-- Latency / Health Chip on Connection -->
        <g transform="translate(${midX}, ${midY})">
          <rect x="-26" y="-10" width="52" height="18" rx="4" fill="#0A0F1D" stroke="${isError ? '#EF4444' : isDegraded ? '#F59E0B' : '#1E293B'}" stroke-width="1" />
          <text x="0" y="3" fill="${isError ? '#F87171' : isDegraded ? '#FBBF24' : '#38BDF8'}" font-size="9.5" font-family="JetBrains Mono, monospace" font-weight="600" text-anchor="middle">${edge.label}</text>
        </g>
      `;
    });

    svg += `</g><!-- Nodes Group --><g class="nodes-group">`;

    for (const [key, n] of Object.entries(this.nodes)) {
      const isSelected = this.selectedNode === key;
      const isFaulted = n.status === "UNHEALTHY" || n.status === "CRITICAL";
      const isDegraded = n.status === "DEGRADED";
      const statusColor = isFaulted ? "#EF4444" : isDegraded ? "#F59E0B" : "#10B981";
      const strokeColor = isSelected ? "#38BDF8" : isFaulted ? "#EF4444" : isDegraded ? "#F59E0B" : "rgba(56, 189, 248, 0.25)";
      const bgFill = isSelected ? "url(#nodeGradSelected)" : isFaulted ? "url(#nodeGradCritical)" : "url(#nodeGradHealthy)";
      const icon = n.icon || "⚡";
      const role = n.role || "Service Node";

      // Pulsing status ring behind node for critical/degraded
      let pulseRing = "";
      if (isFaulted || isDegraded || isSelected) {
        pulseRing = `
          <circle cx="0" cy="0" r="48" fill="none" stroke="${statusColor}" stroke-width="1.5" class="node-pulse-ring" opacity="0.4" />
        `;
      }

      // Badge on top right of node
      let faultBadge = "";
      if (isFaulted) {
        faultBadge = `
          <g transform="translate(45, -34)">
            <rect x="-30" y="-8" width="62" height="16" rx="4" fill="#3D1217" stroke="#EF4444" stroke-width="1" />
            <text x="1" y="4" fill="#F87171" font-size="9" font-weight="700" font-family="JetBrains Mono, monospace" text-anchor="middle">CRITICAL</text>
          </g>
        `;
      } else if (isDegraded) {
        faultBadge = `
          <g transform="translate(45, -34)">
            <rect x="-30" y="-8" width="62" height="16" rx="4" fill="#36220E" stroke="#F59E0B" stroke-width="1" />
            <text x="1" y="4" fill="#FBBF24" font-size="9" font-weight="700" font-family="JetBrains Mono, monospace" text-anchor="middle">DEGRADED</text>
          </g>
        `;
      }

      svg += `
        <g class="node-group" data-service="${key}" transform="translate(${n.x}, ${n.y})" style="cursor: pointer; user-select: none;">
          ${pulseRing}

          <!-- Node Box Card -->
          <rect x="-80" y="-35" width="160" height="70" rx="10" fill="${bgFill}" stroke="${strokeColor}" stroke-width="${isSelected ? 2.5 : 1.2}" filter="${isSelected ? 'url(#glow-cyan)' : isFaulted ? 'url(#glow-red)' : 'none'}" />
          ${faultBadge}

          <!-- Service Icon & Status Ring -->
          <circle cx="-56" cy="-10" r="14" fill="rgba(15, 23, 42, 0.9)" stroke="${strokeColor}" stroke-width="1" />
          <text x="-56" y="-5" font-size="13" text-anchor="middle">${icon}</text>
          <circle cx="-47" cy="-18" r="3.5" fill="${statusColor}" />

          <!-- Service Name & Role -->
          <text x="-36" y="-12" fill="#F1F5F9" font-size="11.5" font-weight="700" font-family="'IBM Plex Sans', sans-serif">${n.label}</text>
          <text x="-36" y="2" fill="#64748B" font-size="9" font-family="'IBM Plex Sans', sans-serif">${role}</text>

          <!-- Footer: Port & Real-Time Latency -->
          <line x1="-70" y1="12" x2="70" y2="12" stroke="rgba(255,255,255,0.06)" stroke-width="1" />
          <text x="-70" y="26" fill="#94A3B8" font-size="9" font-family="JetBrains Mono, monospace">:${n.port}</text>
          <text x="70" y="26" fill="${statusColor}" font-size="9.5" font-weight="600" font-family="JetBrains Mono, monospace" text-anchor="end">${n.latency}ms</text>
        </g>
      `;
    }

    svg += `</g></svg>`;

    // Render interactive overlay toolbar on top of SVG
    const toolbarHtml = `
      <div style="position: absolute; top: 12px; left: 14px; right: 14px; display: flex; align-items: center; justify-content: space-between; pointer-events: none; z-index: 10;">
        <div style="display: flex; align-items: center; gap: 8px; pointer-events: auto;">
          <span style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 12px; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.25); font-size: 11px; font-weight: 600; color: #38bdf8;">
            <span style="width: 7px; height: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 8px #10b981;"></span>
            Live 6-Node Service Mesh
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px; pointer-events: auto; background: rgba(15, 23, 42, 0.85); padding: 4px 10px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); font-size: 10.5px; font-family: monospace;">
          <span style="color: #34d399;">● &lt;30ms</span>
          <span style="color: #fbbf24;">▲ &gt;100ms</span>
          <span style="color: #f87171;">✕ Critical</span>
          <button class="btn btn-ghost btn-xs" onclick="if(window.topology) window.topology.resetAll()" style="padding: 2px 6px; font-size: 10px;">↺ Reset</button>
        </div>
      </div>
    `;

    this.container.innerHTML = toolbarHtml + svg;

    // Attach click listeners to nodes
    this.container.querySelectorAll(".node-group").forEach((el) => {
      el.addEventListener("click", () => {
        const svc = el.getAttribute("data-service");
        this.selectNode(svc);
      });
    });
  }

  selectNode(serviceName) {
    if (!this.nodes[serviceName]) return;
    this.selectedNode = serviceName;
    this.render();
    if (typeof selectServiceCard === "function") {
      selectServiceCard(serviceName);
    }
    if (window.onServiceNodeSelected) {
      window.onServiceNodeSelected(serviceName, this.nodes[serviceName]);
    }
  }

  updateNodeStatus(serviceName, status, latency = null, errorRate = null) {
    if (this.nodes[serviceName]) {
      this.nodes[serviceName].status = status;
      if (latency !== null) this.nodes[serviceName].latency = latency;
      if (errorRate !== null) this.nodes[serviceName].errorRate = errorRate;

      // Update relevant edges
      for (const edge of this.edges) {
        if (edge.to === serviceName || edge.from === serviceName) {
          if (status === "UNHEALTHY" || status === "CRITICAL") {
            edge.status = "error";
            edge.label = latency ? `${latency}ms (5xx)` : "ERR";
          } else if (status === "DEGRADED") {
            edge.status = "degraded";
            edge.label = latency ? `${latency}ms` : "SLOW";
          } else {
            edge.status = "normal";
            edge.label = `${this.nodes[edge.to] ? this.nodes[edge.to].latency : 15}ms`;
          }
        }
      }
      this.render();
    }
  }

  resetAll() {
    for (const k of Object.keys(this.nodes)) {
      this.nodes[k].status = "HEALTHY";
    }
    if (this.nodes["gateway-service"]) this.nodes["gateway-service"].latency = 8;
    if (this.nodes["auth-service"]) this.nodes["auth-service"].latency = 4;
    if (this.nodes["order-service"]) this.nodes["order-service"].latency = 15;
    if (this.nodes["payment-service"]) this.nodes["payment-service"].latency = 22;
    if (this.nodes["inventory-service"]) this.nodes["inventory-service"].latency = 14;
    if (this.nodes["notification-service"]) this.nodes["notification-service"].latency = 9;

    this.edges.forEach(e => {
      e.status = "normal";
      if (this.nodes[e.to]) e.label = `${this.nodes[e.to].latency}ms`;
    });

    this.render();
    if (typeof showToast === "function") {
      showToast("Topology Reset", "All 6 microservice mesh nodes restored to baseline.", "success");
    }
  }
}

window.TopologyRenderer = TopologyRenderer;
