/**
 * Teams module — team settings, member management, invites.
 */
export function createTeamsModule(deps) {
  const { state, elements, api, escapeHtml, icon } = deps;

  async function loadTeams() {
    const data = await api("GET", "/api/teams");
    return data?.items || [];
  }

  async function loadTeamDetail(teamId) {
    return api("GET", `/api/teams/${teamId}`);
  }

  async function createTeam(name) {
    return api("POST", "/api/teams", { name });
  }

  async function renameTeam(teamId, name) {
    return api("PATCH", `/api/teams/${teamId}`, { name });
  }

  async function createInvite(teamId, role = "editor") {
    return api("POST", `/api/teams/${teamId}/invites`, { role, max_uses: 5 });
  }

  async function updateMemberRole(teamId, memberId, role) {
    return api("PATCH", `/api/teams/${teamId}/members/${memberId}/role`, { role });
  }

  async function removeMember(teamId, memberId) {
    return api("DELETE", `/api/teams/${teamId}/members/${memberId}`);
  }

  async function leaveTeam(teamId) {
    return api("POST", `/api/teams/${teamId}/leave`);
  }

  function renderTeamSettings(team) {
    if (!team) return "<p>Нет данных о команде</p>";
    const isOwner = team.role === "owner";

    const membersHtml = (team.members || []).map((m) => {
      const roleLabel = { owner: "Владелец", editor: "Редактор", viewer: "Читатель" }[m.role] || m.role;
      const actions = isOwner && m.telegram_id !== team.created_by
        ? `<button class="btn-sm" data-action="__teams_removeMember" data-args='${JSON.stringify([team.team_id, m.telegram_id])}'>
            ${icon("user-minus", 14)}
          </button>`
        : "";
      return `
        <div class="team-member-row">
          <span class="team-member-id">${m.telegram_id}</span>
          <span class="team-member-role badge">${escapeHtml(roleLabel)}</span>
          ${actions}
        </div>`;
    }).join("");

    const inviteBtn = isOwner
      ? `<button class="btn btn-primary" data-action="__teams_showInvite" data-args='${JSON.stringify([team.team_id])}'>
          ${icon("user-plus", 16)} Пригласить
        </button>`
      : "";

    return `
      <section class="section team-settings-section">
        <h3>${icon("users", 18)} ${escapeHtml(team.name)}</h3>
        <p class="team-role-badge">Ваша роль: <strong>${escapeHtml({ owner: "Владелец", editor: "Редактор", viewer: "Читатель" }[team.role] || team.role)}</strong></p>
        <div class="team-members-list">
          <h4>Участники</h4>
          ${membersHtml}
        </div>
        ${inviteBtn}
      </section>`;
  }

  async function showInvite(teamId) {
    try {
      const result = await createInvite(teamId);
      if (result?.deep_link) {
        const msg = `Ссылка-приглашение:\n${result.deep_link}\n\nОтправьте её коллеге в Telegram.`;
        if (window.Telegram?.WebApp?.showPopup) {
          window.Telegram.WebApp.showPopup({ title: "Приглашение", message: msg, buttons: [{ type: "ok" }] });
        } else {
          alert(msg);
        }
      }
    } catch (e) {
      console.error("Failed to create invite:", e);
    }
  }

  // Team switcher for header
  function renderTeamSwitcher(teams, activeTeamId) {
    if (!teams || teams.length <= 1) return "";
    const options = teams.map((t) =>
      `<option value="${escapeHtml(t.team_id)}"${t.team_id === activeTeamId ? " selected" : ""}>${escapeHtml(t.name)}</option>`
    ).join("");
    return `
      <select class="team-switcher" data-on-change="__teams_switchTeam">
        ${options}
      </select>`;
  }

  function switchTeam(teamId) {
    localStorage.setItem("activeTeamId", teamId);
    state.activeTeamId = teamId;
    // Re-render switcher to update selected option
    renderSwitcherInTopbar(state.teams);
    // Reload current tab content without full page reload
    if (typeof state._reloadCurrentTab === "function") {
      state._reloadCurrentTab();
    }
  }

  function getActiveTeamId() {
    return state.activeTeamId || localStorage.getItem("activeTeamId") || null;
  }

  function renderSwitcherInTopbar(teams) {
    const container = document.querySelector(".topbar-copy");
    if (!container) return;
    const existing = container.querySelector(".team-switcher");
    if (existing) existing.remove();
    if (!teams || teams.length <= 1) return;
    const html = renderTeamSwitcher(teams, getActiveTeamId());
    if (!html) return;
    container.insertAdjacentHTML("beforeend", html);
  }

  async function loadAndRenderSwitcher() {
    const teams = await loadTeams();
    state.teams = teams;
    // Auto-select first team if none active
    if (!state.activeTeamId && teams.length > 0) {
      state.activeTeamId = teams[0].team_id;
      localStorage.setItem("activeTeamId", teams[0].team_id);
    }
    renderSwitcherInTopbar(teams);
    return teams;
  }

  // Expose for inline onclick handlers
  window.__teams = { showInvite, removeMember, switchTeam };
  window.__teams_removeMember = removeMember;
  window.__teams_showInvite = showInvite;
  window.__teams_switchTeam = switchTeam;

  return {
    loadTeams,
    loadTeamDetail,
    createTeam,
    renameTeam,
    createInvite,
    updateMemberRole,
    removeMember,
    leaveTeam,
    renderTeamSettings,
    renderTeamSwitcher,
    renderSwitcherInTopbar,
    loadAndRenderSwitcher,
    switchTeam,
    getActiveTeamId,
  };
}
