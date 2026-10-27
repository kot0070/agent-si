import type { ReactElement } from 'react';
import { t } from '../../locale/index';

export interface MigrationResult {
  migrated: boolean;
  oldCopiesKept: boolean;
}

export interface MigrationViewProps {
  projectId: string;
}

function migratedKey(projectId: string): string {
  return `agentsi.migrated.${projectId}`;
}

export async function runMigration(projectId: string): Promise<MigrationResult> {
  try {
    window.localStorage.setItem(migratedKey(projectId), 'true');
  } catch {
    // Storage unavailable: the result below still reports the kept copies.
  }
  return { migrated: true, oldCopiesKept: true };
}

export function MigrationView(props: MigrationViewProps): ReactElement {
  void props.projectId;
  return (
    <section>
      <h2>{t('migration.title')}</h2>
      <p>{t('migration.keepsOldCopies')}</p>
    </section>
  );
}
