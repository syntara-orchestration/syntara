import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ProjectState = {
  /** The currently selected project ID, or null for no selection. */
  selectedProjectId: string | null
  /** Display name of the selected project. Persisted so the toggle shows the correct name even while the project is filtered out of the typeahead results. */
  selectedProjectName: string | null
  /** Set the selected project. Pass null to clear. Optionally provide the project name so the toggle remains stable while the project is not in the current filter results. */
  setSelectedProjectId: (projectId: string | null, name?: string | null) => void
  /** Persist the display name of the currently selected project without touching the ID. Used to keep the toggle label stable while the project is absent from filtered results. */
  setSelectedProjectName: (name: string | null) => void
  /**
   * Project IDs the user has marked as favorites (order = display priority: earlier = higher in list).
   * Persisted with selected project for quick access in the project selector.
   */
  favoriteProjectIds: string[]
  /** Toggle favorite for a project ID (PatternFly Select favorites pattern). */
  toggleFavoriteProjectId: (projectId: string) => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      selectedProjectId: null,
      selectedProjectName: null,
      favoriteProjectIds: [],
      setSelectedProjectId: (projectId, name) =>
        set({ selectedProjectId: projectId, selectedProjectName: name ?? null }),
      setSelectedProjectName: (name) => set({ selectedProjectName: name }),
      toggleFavoriteProjectId: (projectId) =>
        set((s) => {
          const i = s.favoriteProjectIds.indexOf(projectId)
          if (i >= 0) {
            return { favoriteProjectIds: s.favoriteProjectIds.filter((id) => id !== projectId) }
          }
          return { favoriteProjectIds: [...s.favoriteProjectIds, projectId] }
        }),
    }),
    { name: 'syntara-selected-project', version: 1 }
  )
)
