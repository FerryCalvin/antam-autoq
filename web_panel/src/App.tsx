import React, { useState, useEffect, useRef } from 'react';
import { Play, Square, Trash2, Plus, Terminal, Settings, Server, CheckCircle, Activity, Eye, EyeOff } from 'lucide-react';

// Define types for our data
interface AccountNode {
  id: number;
  nama_lengkap: string;
  nik: string;
  no_hp: string;
  email: string;
  target_location: string;
  target_date: string;
  proxy?: string;
  is_active: boolean;
  status_message: string;
}

function App() {
  const [nodes, setNodes] = useState<AccountNode[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [soundEnabled, setSoundEnabled] = useState(false);

  // Form State
  const [newNama, setNewNama] = useState('');
  const [newNik, setNewNik] = useState('');
  const [newNoHp, setNewNoHp] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newLocation, setNewLocation] = useState('SUB-01');
  const [newDate, setNewDate] = useState('2026-03-01');
  const [newProxy, setNewProxy] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const ws = useRef<WebSocket | null>(null);

  // Fetch nodes
  const fetchNodes = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/nodes');
      const data = await res.json();
      setNodes(data);
    } catch (e) {
      console.error(e);
    }
  };

  // WebSocket Setup
  useEffect(() => {
    fetchNodes();

    // Connect WS
    const connectWs = () => {
      ws.current = new WebSocket('ws://localhost:8000/ws');

      ws.current.onmessage = (event) => {
        setLogs(prev => [...prev, event.data]);
      };

      ws.current.onclose = () => {
        setTimeout(connectWs, 3000); // Reconnect
      };
    };

    connectWs();
    return () => ws.current?.close();
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const addNode = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await fetch('http://localhost:8000/api/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nama_lengkap: newNama,
          nik: newNik,
          no_hp: newNoHp,
          email: newEmail,
          password: newPassword,
          target_location: newLocation,
          target_date: newDate,
          proxy: newProxy || null
        })
      });
      setNewNama(''); setNewNik(''); setNewNoHp(''); setNewEmail(''); setNewPassword(''); setNewProxy('');
      fetchNodes();
    } catch (e) { console.error(e); }
  };

  const deleteNode = async (id: number) => {
    await fetch(`http://localhost:8000/api/nodes/${id}`, { method: 'DELETE' });
    fetchNodes();
  };

  const startNode = async (id: number) => {
    await fetch(`http://localhost:8000/api/nodes/${id}/start`, { method: 'POST' });
    fetchNodes();
  };

  const stopNode = async (id: number) => {
    await fetch(`http://localhost:8000/api/nodes/${id}/stop`, { method: 'POST' });
    fetchNodes();
  };

  const startAll = () => {
    nodes.filter(n => !n.is_active).forEach(n => startNode(n.id));
  };

  const stopAll = () => {
    nodes.filter(n => n.is_active).forEach(n => stopNode(n.id));
  };

  // Stats
  const activeCount = nodes.filter(n => n.is_active).length;
  const readyCount = nodes.length - activeCount;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300 font-sans p-6 grid grid-cols-12 gap-6">

      {/* LEFT PANE - Account Nodes */}
      <div className="col-span-12 lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-[90vh]">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Server size={20} className="text-blue-500" /> Account Nodes
          </h2>
          <div className="text-xs bg-slate-800 px-2 py-1 rounded-md">{nodes.length} Total</div>
        </div>

        {/* Add Node Form */}
        <form onSubmit={addNode} className="bg-slate-800/50 p-4 rounded-lg mb-4 space-y-3 border border-slate-800">
          <div className="grid grid-cols-2 gap-3">
            <input required placeholder="Nama Lengkap KTP" value={newNama} onChange={e => setNewNama(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
            <input required type="number" placeholder="Nomor Induk Kependudukan (NIK)" value={newNik} onChange={e => setNewNik(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <input required type="number" placeholder="Nomor Handphone (08...)" value={newNoHp} onChange={e => setNewNoHp(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
            <input required type="email" placeholder="Email" value={newEmail} onChange={e => setNewEmail(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
          </div>
          <div className="grid grid-cols-1 gap-3">
            <div className="relative">
              <input required type={showPassword ? "text" : "password"} placeholder="Password Akun Antam" value={newPassword} onChange={e => setNewPassword(e.target.value)} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500 pr-10" />
              <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <select value={newLocation} onChange={e => setNewLocation(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500">
              <option value="JKT-06">ATGM-Gedung Antam</option>
              <option value="JKT-01">ATGM-Graha Dipta</option>
              <option value="BPN-01">Butik Emas LM - Balikpapan</option>
              <option value="BDG-01">Butik Emas LM - Bandung</option>
              <option value="BKS-01">Butik Emas LM - Bekasi</option>
              <option value="TGR-01">Butik Emas LM - Bintaro</option>
              <option value="BGR-01">Butik Emas LM - Bogor</option>
              <option value="DPS-01">Butik Emas LM - Denpasar</option>
              <option value="SDA-01">Butik Emas LM - Djuanda</option>
              <option value="JKT-04">Butik Emas LM - Gedung Antam</option>
              <option value="JKT-05">Butik Emas LM - Graha Dipta</option>
              <option value="MKS-01">Butik Emas LM - Makassar</option>
              <option value="MDN-01">Butik Emas LM - Medan</option>
              <option value="PLB-01">Butik Emas LM - Palembang</option>
              <option value="PKU-01">Butik Emas LM - Pekanbaru</option>
              <option value="JKT-07">Butik Emas LM - Puri Indah</option>
              <option value="SMR-01">Butik Emas LM - Semarang</option>
              <option value="TGR-02">Butik Emas LM - Serpong</option>
              <option value="JKT-08">Butik Emas LM - Setiabudi One</option>
              <option value="SUB-01">Butik Emas LM - Surabaya 1 Darmo</option>
              <option value="SUB-02">Butik Emas LM - Surabaya 2 Pakuwon</option>
              <option value="YOG-01">Butik Emas LM - Yogyakarta</option>
            </select>
            <input required type="text" placeholder="Tanggal (YYYY-MM-DD)" value={newDate} onChange={e => setNewDate(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500" />
            <input placeholder="Proxy (Optional) http://..." value={newProxy} onChange={e => setNewProxy(e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500 col-span-2" />
          </div>
          <button type="submit" className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 rounded-md transition flex justify-center items-center gap-2 text-sm">
            <Plus size={16} /> Add Node
          </button>
        </form>

        {/* Nodes List */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-thin scrollbar-thumb-slate-700">
          {nodes.map(node => (
            <div key={node.id} className="bg-slate-800 border border-slate-700 rounded-lg p-3 flex flex-col gap-2">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold text-white">{node.nama_lengkap}</div>
                  <div className="text-xs text-slate-400 mt-1">🆔 NIK: {node.nik} | 📍 {node.target_location} ({node.target_date})</div>
                  <div className={`text-xs mt-1 font-medium ${node.is_active ? 'text-green-400' : 'text-slate-500'}`}>
                    Status: {node.status_message}
                  </div>
                </div>
                <div className="flex gap-2">
                  {!node.is_active ? (
                    <button onClick={() => startNode(node.id)} className="p-2 bg-green-500/10 text-green-500 hover:bg-green-500 hover:text-white rounded transition" title="Start Node">
                      <Play size={16} fill="currentColor" />
                    </button>
                  ) : (
                    <button onClick={() => stopNode(node.id)} className="p-2 bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white rounded transition" title="Stop Node">
                      <Square size={16} fill="currentColor" />
                    </button>
                  )}
                  <button onClick={() => deleteNode(node.id)} className="p-2 bg-slate-700/50 text-slate-400 hover:text-red-400 rounded transition" title="Delete">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
          {nodes.length === 0 && <div className="text-center text-slate-500 mt-10 text-sm">No accounts added yet.</div>}
        </div>

        {/* Global Controls */}
        <div className="mt-4 grid grid-cols-2 gap-3 pt-4 border-t border-slate-800">
          <button onClick={startAll} className="bg-green-600 hover:bg-green-500 text-white py-2 rounded font-medium text-sm transition">Jalankan Semua</button>
          <button onClick={stopAll} className="bg-red-600 hover:bg-red-500 text-white py-2 rounded font-medium text-sm transition">Hentikan Semua</button>
        </div>
      </div>

      {/* RIGHT PANE */}
      <div className="col-span-12 lg:col-span-7 flex flex-col gap-6 h-[90vh]">

        {/* Top Stats Bar & Settings */}
        <div className="grid grid-cols-2 gap-6">
          {/* Stats */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
              <div className="bg-blue-500/20 p-3 rounded-lg text-blue-500"><Activity size={24} /></div>
              <div><div className="text-2xl font-bold text-white">{activeCount}</div><div className="text-xs text-slate-400">Active Bots</div></div>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
              <div className="bg-slate-700/50 p-3 rounded-lg text-slate-300"><CheckCircle size={24} /></div>
              <div><div className="text-2xl font-bold text-white">{readyCount}</div><div className="text-xs text-slate-400">Ready to Run</div></div>
            </div>
          </div>

          {/* Settings Sub-panel */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-center">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold flex items-center gap-2"><Settings size={16} /> Settings</div>
              <label className="flex items-center cursor-pointer gap-2 text-xs">
                <input type="checkbox" className="sr-only peer" checked={soundEnabled} onChange={() => setSoundEnabled(!soundEnabled)} />
                <div className="w-8 h-4 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-blue-500 relative"></div>
                Notifikasi Suara
              </label>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setLogs([])} className="flex-1 bg-slate-800 hover:bg-slate-700 text-xs py-2 rounded transition border border-slate-700 text-slate-300">Bersihkan Log</button>
              <button className="flex-1 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-900/50 text-xs py-2 rounded transition">Hapus Semua Profil</button>
            </div>
          </div>
        </div>

        {/* Live Output Terminal */}
        <div className="bg-[#0D1117] border border-slate-800 rounded-xl flex-1 flex flex-col overflow-hidden">
          <div className="bg-slate-900/80 border-b border-slate-800 px-4 py-3 flex items-center gap-2 text-sm font-semibold shadow-sm">
            <Terminal size={16} className="text-slate-400" /> Live Terminal Output
          </div>
          <div className="flex-1 overflow-y-auto p-4 font-mono text-sm space-y-1">
            {logs.map((log, i) => {
              // Pseudo coloring logic based on keywords
              let color = 'text-slate-400'
              if (log.includes('🔴')) color = 'text-red-400'
              else if (log.includes('🟢') || log.includes('Success')) color = 'text-green-400'
              else if (log.includes('⏳')) color = 'text-yellow-400'
              else if (log.includes('⚙️') || log.includes('System')) color = 'text-blue-400'

              return <div key={i} className={`${color} leading-relaxed`}>{log}</div>
            })}
            <div ref={logsEndRef} />
          </div>
        </div>

      </div>
    </div>
  );
}

export default App;
