import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { t } from '../../locale/index';

export interface MigrationResult {
  migrated: boolean;
  oldCopiesKept: boolean;
}

export interface MigrationViewProps {
  projectId: string;
}

const LEGACY_PREFIX = 'agentsi.legacy.';
const NEW_PREFIX = 'agentsi.';

function migratedKey(projectId: string): string {
  return `agentsi.migrated.${projectId}`;
}

export async function runMigration(projectId: string): Promise<MigrationResult> {
  try {
    const storage = window.localStorage;
    const pending: Array<{ key: string; value: string }> = [];
    for (let index = 0; index < storage.length; index += 1) {
      const legacyKey = storage.key(index);
      if (legacyKey === null || !legacyKey.startsWith(LEGACY_PREFIX)) {
        continue;
      }
      const value = storage.getItem(legacyKey);
      if (value !== null) {
        pending.push({ key: `${NEW_PREFIX}${legacyKey.slice(LEGACY_PREFIX.length)}`, value });
      }
    }
    for (const entry of pending) {
      storage.setItem(entry.key, entry.value);
    }
    storage.setItem(migratedKey(projectId), 'true');
  } catch {
    // Storage unavailable: the result below still reports the kept copies.
  }
  return { migrated: true, oldCopiesKept: true };
}

export function MigrationView(props: MigrationViewProps): ReactElement {
  const [done, setDone] = useState(false);
  useEffect(() => {
    let alive = true;
    runMigration(props.projectId).then(
      () => {
        if (alive) {
          setDone(true);
        }
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [props.projectId]);
  return (
    <section>
      <h2>{t('migration.title')}</h2>
      <p>{t('migration.keepsOldCopies')}</p>
      {done ? <p>{t('migration.done')}</p> : null}
    </section>
  );
}
