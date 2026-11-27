import { api } from "./api";

// Studio Projects: persistent source trees that chosen Agents edit in
// place through sequential coordination runs (backend đợt 1, PR #149).
const base = "/ai/studio-projects";
const projectPath = (id) => `${base}/${encodeURIComponent(id)}`;

export const studioProjectsService = {
  async list(signal) {
    const { data } = await api.get(base, { signal });
    return data.projects;
  },
  async create(payload, signal) {
    const { data } = await api.post(base, payload, { signal });
    return data;
  },
  async importZip(file, name, signal) {
    const form = new FormData();
    form.append("file", file);
    if (name) form.append("name", name);
    const { data } = await api.post(`${base}/import-zip`, form, { signal });
    return data;
  },
  async get(id, signal) {
    const { data } = await api.get(projectPath(id), { signal });
    return data;
  },
  async patch(id, payload, signal) {
    const { data } = await api.patch(projectPath(id), payload, { signal });
    return data;
  },
  async remove(id) {
    await api.delete(projectPath(id));
  },
  async listFiles(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/files`, { signal });
    return data.files;
  },
  async getFile(id, path, signal) {
    const { data } = await api.get(`${projectPath(id)}/file`, {
      params: { path },
      signal,
    });
    return data;
  },
  async saveFile(id, path, content, signal) {
    const { data } = await api.put(
      `${projectPath(id)}/file`,
      { content },
      { params: { path }, signal },
    );
    return data;
  },
  async removeFile(id, path) {
    await api.delete(`${projectPath(id)}/file`, { params: { path } });
  },
  async exportZip(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/export.zip`, {
      responseType: "blob",
      signal,
    });
    return data;
  },
  async listChanges(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/changes`, { signal });
    return data.changes;
  },
  async listRuns(id, signal) {
    const { data } = await api.get(`${projectPath(id)}/runs`, { signal });
    return data.runs;
  },
  async run(id, payload, signal) {
    const { data } = await api.post(`${projectPath(id)}/runs`, payload, {
      signal,
    });
    return data;
  },
};
