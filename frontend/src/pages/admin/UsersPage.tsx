/**
 * Users CRUD — admin only. A staff token gets 403 from the backend, and the
 * Usuarios tab is hidden for them.
 *
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  FiEdit2,
  FiKey,
  FiPlus,
  FiRefreshCw,
  FiShield,
  FiTrash2,
  FiUserCheck,
  FiUsers,
  FiUserX,
} from 'react-icons/fi'
import { Badge } from '@/components/common/Badge'
import { Button } from '@/components/common/Button'
import { adminService } from '@/services/adminService'
import { useAuth } from '@/stores/authContext'
import {
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  StatTile,
  TableSkeleton,
} from '@/components/admin/uiKit'
import type { AdminUser, UserRole, UserUpdateRequest } from '@/types/admin'

const ROLE_LABEL: Record<UserRole, string> = {
  admin: 'Administrador',
  staff: 'Personal',
  user: 'Usuario',
}

const ROLE_VARIANT: Record<UserRole, 'red' | 'blue' | 'gray'> = {
  admin: 'red',
  staff: 'blue',
  user: 'gray',
}

/** Mirrors the backend's minimum; a shorter one is rejected with a 422. */
const MIN_PASSWORD = 8

interface FormState {
  username: string
  password: string
  role: UserRole
  full_name: string
  email: string
  phone_number: string
  active: boolean
}

const EMPTY_FORM: FormState = {
  username: '',
  password: '',
  role: 'staff',
  full_name: '',
  email: '',
  phone_number: '',
  active: true,
}

export const UsersPage: React.FC = () => {
  const { user: me } = useAuth()

  const [rows, setRows] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [resetting, setResetting] = useState<AdminUser | null>(null)
  const [deleting, setDeleting] = useState<AdminUser | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [newPassword, setNewPassword] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await adminService.listUsers({ limit: 200 })
      setRows(data.users)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error cargando usuarios.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const activeAdmins = useMemo(
    () => rows.filter((u) => u.role === 'admin' && u.active),
    [rows],
  )

  /**
   * Why a destructive action is blocked, or null when it is allowed. Mirrors
   * the backend's two invariants so the admin is told up front.
   */
  const blockReason = (target: AdminUser, kind: 'demote' | 'delete'): string | null => {
    const isSelf = target.username === me?.username
    if (isSelf) {
      return kind === 'delete'
        ? 'No puedes eliminar tu propia cuenta.'
        : 'No puedes cambiar tu propio rol ni desactivarte.'
    }
    if (
      target.role === 'admin' &&
      target.active &&
      activeAdmins.length <= 1
    ) {
      return 'Es el único administrador activo. Crea otro administrador primero.'
    }
    return null
  }

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setActionError(null)
    try {
      await fn()
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'La operación falló.',
      )
    } finally {
      setBusy(false)
    }
  }

  const handleCreate = () =>
    run(async () => {
      await adminService.createUser({
        username: form.username.trim(),
        password: form.password,
        role: form.role,
        full_name: form.full_name.trim() || null,
        email: form.email.trim() || null,
        phone_number: form.phone_number.trim() || null,
        active: form.active,
      })
      setCreating(false)
      setForm(EMPTY_FORM)
      await load()
    })

  const handleEdit = () =>
    run(async () => {
      if (!editing) return
      // Only the keys that actually changed: exclude_unset means an omitted
      // field is left alone, and sending everything would blank untouched ones.
      const changes: UserUpdateRequest = {}
      if (form.role !== editing.role) changes.role = form.role
      if (form.active !== editing.active) changes.active = form.active
      if (form.full_name !== (editing.fullName ?? ''))
        changes.full_name = form.full_name.trim() || null
      if (form.email !== (editing.email ?? ''))
        changes.email = form.email.trim() || null
      if (form.phone_number !== (editing.phoneNumber ?? ''))
        changes.phone_number = form.phone_number.trim() || null

      if (Object.keys(changes).length > 0) {
        await adminService.updateUser(editing.username, changes)
      }
      setEditing(null)
      await load()
    })

  const handleReset = () =>
    run(async () => {
      if (!resetting) return
      await adminService.updateUser(resetting.username, {
        password: newPassword,
      })
      setResetting(null)
      setNewPassword('')
    })

  const handleToggleActive = (target: AdminUser) =>
    run(async () => {
      await adminService.updateUser(target.username, { active: !target.active })
      await load()
    })

  const handleDelete = () =>
    run(async () => {
      if (!deleting) return
      await adminService.deleteUser(deleting.username)
      setDeleting(null)
      await load()
    })

  const openEdit = (target: AdminUser) => {
    setForm({
      username: target.username,
      password: '',
      role: target.role,
      full_name: target.fullName ?? '',
      email: target.email ?? '',
      phone_number: target.phoneNumber ?? '',
      active: target.active,
    })
    setEditing(target)
  }

  const field =
    'mt-1 w-full border-2 border-brand-navy/20 focus:border-brand-yellow rounded-lg px-3 py-2 text-brand-navy outline-none'
  const label = 'text-brand-navy/70 text-xs uppercase font-semibold'

  return (
    <div className="max-w-6xl mx-auto">
      <PageHeader
        title="Usuarios"
        subtitle={`${rows.length} cuenta(s) · ${activeAdmins.length} administrador(es) activo(s)`}
        icon={<FiUsers className="w-6 h-6" />}
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<FiRefreshCw className="w-4 h-4" />}
              onClick={() => void load()}
            >
              Actualizar
            </Button>
            <Button
              variant="yellow"
              size="sm"
              icon={<FiPlus className="w-4 h-4" />}
              onClick={() => {
                setForm(EMPTY_FORM)
                setCreating(true)
              }}
            >
              Nuevo usuario
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <StatTile
          label="Cuentas"
          value={rows.length}
          tone="navy"
          icon={<FiUsers className="w-7 h-7" />}
        />
        <StatTile
          label="Administradores activos"
          value={activeAdmins.length}
          tone="red"
          icon={<FiShield className="w-7 h-7" />}
        />
        <StatTile
          label="Activas"
          value={rows.filter((u) => u.active).length}
          tone="blue"
          icon={<FiUserCheck className="w-7 h-7" />}
        />
      </div>

      {actionError && (
        <div className="mb-4">
          <ErrorState message={actionError} />
        </div>
      )}

      <div className="bg-white rounded-xl border-2 border-brand-navy/10 overflow-hidden">
        {loading ? (
          <div className="px-4">
            <TableSkeleton />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState message={error} onRetry={() => void load()} />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState message="No hay usuarios" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brand-navy text-white">
                <tr>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Usuario
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Contacto
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Rol
                  </th>
                  <th className="text-left px-4 py-2.5 font-display tracking-wider uppercase">
                    Estado
                  </th>
                  <th className="text-right px-4 py-2.5 font-display tracking-wider uppercase">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => {
                  const isSelf = u.username === me?.username
                  const demoteBlock = blockReason(u, 'demote')
                  const deleteBlock = blockReason(u, 'delete')
                  return (
                    <tr
                      key={u.username}
                      className="border-b border-brand-navy/10 hover:bg-brand-yellow/10 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="font-semibold text-brand-navy font-mono">
                          {u.username}
                          {isSelf && (
                            <span className="ml-2 text-brand-blue text-xs font-sans">
                              (tú)
                            </span>
                          )}
                        </div>
                        {u.fullName && (
                          <div className="text-brand-navy/60 text-xs">
                            {u.fullName}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-brand-navy/70 text-xs">
                        <div>{u.email || '—'}</div>
                        <div>{u.phoneNumber || '—'}</div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={ROLE_VARIANT[u.role]}>
                          {ROLE_LABEL[u.role]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        {u.active ? (
                          <Badge variant="green">Activa</Badge>
                        ) : (
                          <Badge variant="gray">Inactiva</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1 flex-wrap">
                          <Button
                            size="sm"
                            variant="secondary"
                            icon={<FiEdit2 className="w-3.5 h-3.5" />}
                            onClick={() => openEdit(u)}
                          >
                            Editar
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="!text-brand-navy !border-brand-navy/30"
                            icon={<FiKey className="w-3.5 h-3.5" />}
                            onClick={() => {
                              setNewPassword('')
                              setResetting(u)
                            }}
                          >
                            Clave
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="!text-brand-navy !border-brand-navy/30"
                            icon={
                              u.active ? (
                                <FiUserX className="w-3.5 h-3.5" />
                              ) : (
                                <FiUserCheck className="w-3.5 h-3.5" />
                              )
                            }
                            disabled={u.active && demoteBlock !== null}
                            title={
                              u.active ? demoteBlock ?? undefined : undefined
                            }
                            onClick={() => void handleToggleActive(u)}
                          >
                            {u.active ? 'Desactivar' : 'Activar'}
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            icon={<FiTrash2 className="w-3.5 h-3.5" />}
                            disabled={deleteBlock !== null}
                            title={deleteBlock ?? undefined}
                            onClick={() => setDeleting(u)}
                          >
                            Eliminar
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-brand-navy/50 text-xs mt-3">
        El último administrador activo no puede eliminarse, desactivarse ni
        degradarse — dejaría el panel sin acceso. Tampoco puedes modificar tu
        propio rol.
      </p>

      {/* Create */}
      {creating && (
        <Modal title="Nuevo usuario" onClose={() => setCreating(false)}>
          <div className="space-y-3">
            <label className="block">
              <span className={label}>Usuario *</span>
              <input
                className={field}
                value={form.username}
                autoFocus
                onChange={(e) =>
                  setForm((f) => ({ ...f, username: e.target.value }))
                }
                placeholder="secretaria"
              />
              <span className="text-brand-navy/50 text-xs">
                Se guarda en minúsculas; el inicio de sesión no distingue
                mayúsculas.
              </span>
            </label>
            <label className="block">
              <span className={label}>Contraseña * (mín. {MIN_PASSWORD})</span>
              <input
                className={field}
                type="password"
                value={form.password}
                onChange={(e) =>
                  setForm((f) => ({ ...f, password: e.target.value }))
                }
              />
            </label>
            <label className="block">
              <span className={label}>Rol</span>
              <select
                className={`${field} bg-white`}
                value={form.role}
                onChange={(e) =>
                  setForm((f) => ({ ...f, role: e.target.value as UserRole }))
                }
              >
                <option value="staff">Personal (citas)</option>
                <option value="admin">Administrador (todo)</option>
                <option value="user">Usuario (sin panel)</option>
              </select>
            </label>
            <label className="block">
              <span className={label}>Nombre completo</span>
              <input
                className={field}
                value={form.full_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, full_name: e.target.value }))
                }
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className={label}>Correo</span>
                <input
                  className={field}
                  type="email"
                  value={form.email}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, email: e.target.value }))
                  }
                />
              </label>
              <label className="block">
                <span className={label}>Teléfono</span>
                <input
                  className={field}
                  value={form.phone_number}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, phone_number: e.target.value }))
                  }
                />
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="ghost"
                className="!text-brand-navy !border-brand-navy/30"
                onClick={() => setCreating(false)}
              >
                Cancelar
              </Button>
              <Button
                variant="yellow"
                loading={busy}
                disabled={
                  !form.username.trim() || form.password.length < MIN_PASSWORD
                }
                onClick={() => void handleCreate()}
              >
                Crear
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Edit  */}
      {editing && (
        <Modal
          title={`Editar ${editing.username}`}
          onClose={() => setEditing(null)}
        >
          <div className="space-y-3">
            <label className="block">
              <span className={label}>Rol</span>
              <select
                className={`${field} bg-white`}
                value={form.role}
                disabled={blockReason(editing, 'demote') !== null}
                onChange={(e) =>
                  setForm((f) => ({ ...f, role: e.target.value as UserRole }))
                }
              >
                <option value="staff">Personal (citas)</option>
                <option value="admin">Administrador (todo)</option>
                <option value="user">Usuario (sin panel)</option>
              </select>
              {blockReason(editing, 'demote') && (
                <span className="text-brand-red text-xs">
                  {blockReason(editing, 'demote')}
                </span>
              )}
            </label>
            <label className="block">
              <span className={label}>Nombre completo</span>
              <input
                className={field}
                value={form.full_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, full_name: e.target.value }))
                }
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className={label}>Correo</span>
                <input
                  className={field}
                  type="email"
                  value={form.email}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, email: e.target.value }))
                  }
                />
              </label>
              <label className="block">
                <span className={label}>Teléfono</span>
                <input
                  className={field}
                  value={form.phone_number}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, phone_number: e.target.value }))
                  }
                />
              </label>
            </div>
            <label className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                checked={form.active}
                disabled={form.active && blockReason(editing, 'demote') !== null}
                onChange={(e) =>
                  setForm((f) => ({ ...f, active: e.target.checked }))
                }
                className="w-4 h-4 accent-brand-yellow"
              />
              <span className="text-brand-navy text-sm font-semibold">
                Cuenta activa
              </span>
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="ghost"
                className="!text-brand-navy !border-brand-navy/30"
                onClick={() => setEditing(null)}
              >
                Cancelar
              </Button>
              <Button
                variant="yellow"
                loading={busy}
                onClick={() => void handleEdit()}
              >
                Guardar
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Password reset  */}
      {resetting && (
        <Modal
          title={`Nueva contraseña · ${resetting.username}`}
          onClose={() => setResetting(null)}
        >
          <div className="space-y-3">
            <label className="block">
              <span className={label}>Contraseña (mín. {MIN_PASSWORD})</span>
              <input
                className={field}
                type="password"
                autoFocus
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </label>
            <p className="text-brand-navy/60 text-xs">
              Se guarda únicamente el hash argon2id. La contraseña anterior deja
              de funcionar de inmediato.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="ghost"
                className="!text-brand-navy !border-brand-navy/30"
                onClick={() => setResetting(null)}
              >
                Cancelar
              </Button>
              <Button
                variant="yellow"
                loading={busy}
                disabled={newPassword.length < MIN_PASSWORD}
                onClick={() => void handleReset()}
              >
                Cambiar
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/*  Delete  */}
      {deleting && (
        <ConfirmDialog
          title="Eliminar usuario"
          danger
          busy={busy}
          confirmLabel="Eliminar"
          message={
            <>
              Se eliminará la cuenta <strong>{deleting.username}</strong> de
              forma permanente.
              <p className="mt-2">
                Considera <strong>desactivarla</strong> en su lugar: conserva el
                historial de acceso y puede reactivarse.
              </p>
            </>
          }
          onCancel={() => setDeleting(null)}
          onConfirm={() => void handleDelete()}
        />
      )}
    </div>
  )
}

export default UsersPage
