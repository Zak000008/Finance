const api = {
  async health() {
    return request("/api/health");
  },

  async listTransazioni() {
    return request("/api/transazioni");
  },

  async getStorico(periodo) {
    return request(`/api/storico?periodo=${encodeURIComponent(periodo)}`);
  },

  async createTransazione(transazione) {
    return request("/api/transazioni", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(transazione)
    });
  },

  async updateTransazione(id, transazione) {
    return request(`/api/transazioni/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(transazione)
    });
  },

  async deleteTransazione(id) {
    return request(`/api/transazioni/${id}`, {
      method: "DELETE"
    });
  },

  async listObiettivi() {
    return request("/api/obiettivi");
  },

  async createObiettivo(obiettivo) {
    return request("/api/obiettivi", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(obiettivo)
    });
  },

  async updateObiettivo(id, obiettivo) {
    return request(`/api/obiettivi/${id}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(obiettivo)
    });
  },

  async deleteObiettivo(id) {
    return request(`/api/obiettivi/${id}`, {
      method: "DELETE"
    });
  },

  async analisiAi(periodo) {
    return request("/api/ai/analisi", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ periodo })
    });
  },

  async downloadExportCsv(month) {
    const response = await fetch(`/api/export/csv?month=${encodeURIComponent(month)}`);
    if (!response.ok) {
      let message = "Errore durante l'esportazione.";
      try {
        const data = await response.json();
        message = data.error || message;
      } catch {
        // CSV error body may not be JSON
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const filename = parseFilename(response) || `report_${month}.csv`;
    return { blob, filename };
  }
};

function parseFilename(response) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i);
  return match ? match[1] : null;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Errore nella richiesta.");
  }

  return data;
}
