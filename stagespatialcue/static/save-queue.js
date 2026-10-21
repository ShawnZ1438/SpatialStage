/* Single-flight, latest-state save queue. No network or DOM dependencies. */
'use strict';
class ProjectSaveQueue {
  constructor({snapshot, persist, onState=()=>{}, onSaved=()=>{}}) {
    Object.assign(this, {snapshot, persist, onState, onSaved});
    this.revision = 0;
    this.savedRevision = 0;
    this.running = null;
  }
  get dirty() { return this.savedRevision !== this.revision; }
  changed() { this.revision++; this.onState('dirty'); }
  flush() {
    if (this.running) return this.running;
    this.running = this.drain().finally(()=>{this.running=null;});
    return this.running;
  }
  async drain() {
    try {
      while (this.dirty) {
        const revision = this.revision;
        const snapshot = structuredClone(this.snapshot());
        if (!snapshot) throw new Error('Cannot save without a project');
        this.onState('saving');
        const result = await this.persist(snapshot);
        this.savedRevision = revision;
        this.onSaved(snapshot, result, !this.dirty);
      }
      this.onState('saved');
    } catch(error) {
      this.onState('error'); // preserve dirty revision; retry is explicit
      throw error;
    }
  }
}
if (typeof module !== 'undefined') module.exports = {ProjectSaveQueue};
