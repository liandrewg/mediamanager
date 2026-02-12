import client from './client'

export async function getTunnelStatus() {
  const { data } = await client.get('/admin/tunnel')
  return data as { active: boolean; url: string | null }
}

export async function startTunnel() {
  const { data } = await client.post('/admin/tunnel/start')
  return data as { active: boolean; url: string | null }
}

export async function stopTunnel() {
  const { data } = await client.post('/admin/tunnel/stop')
  return data as { active: boolean; url: string | null }
}
