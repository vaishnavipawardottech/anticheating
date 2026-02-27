import React, { useEffect, useState } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts';
import {
    Library, ClipboardList, Database, GraduationCap,
    TrendingUp, Calendar
} from 'lucide-react';
import { authFetch } from '../utils/api';
import dayjs from 'dayjs';
import './Dashboard.css';

// ─── helpers ──────────────────────────────────────────────────────────────────

const getExamStatus = (exam) => {
    const now = dayjs();
    if (now.isBefore(dayjs(exam.start_time))) return 'upcoming';
    if (now.isAfter(dayjs(exam.end_time))) return 'ended';
    return 'live';
};

const STATUS_COLOR = {
    live: '#059669',
    upcoming: '#0061a1',
    ended: '#9CA3AF',
};

const STATUS_BG = {
    live: '#D1FAE5',
    upcoming: '#DBEAFE',
    ended: '#F3F4F6',
};

const STATUS_LABEL = { live: 'Live', upcoming: 'Upcoming', ended: 'Ended' };

// ─── custom tooltip ───────────────────────────────────────────────────────────

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="dash-tooltip">
            <p className="dash-tooltip-label">{label}</p>
            {payload.map((entry, i) => (
                <p key={i} style={{ color: entry.color || '#111827' }}>
                    {entry.name}: <strong>{entry.value}</strong>
                </p>
            ))}
        </div>
    );
};

// ─── stat card ────────────────────────────────────────────────────────────────

const StatCard = ({ icon: Icon, label, value, sub, accent }) => (
    <div className="dash-stat-card">
        <div className="dash-stat-icon" style={{ background: accent + '18', color: accent }}>
            <Icon size={18} />
        </div>
        <div className="dash-stat-body">
            <div className="dash-stat-value">{value ?? '—'}</div>
            <div className="dash-stat-label">{label}</div>
            {sub && <div className="dash-stat-sub">{sub}</div>}
        </div>
    </div>
);

// ─── component ────────────────────────────────────────────────────────────────

const Dashboard = () => {
    const [subjects, setSubjects] = useState([]);
    const [exams, setExams] = useState([]);
    const [poolCount, setPoolCount] = useState(null);
    const [studentCount, setStudentCount] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchAll = async () => {
            try {
                const [subRes, examRes, poolRes, stuRes] = await Promise.allSettled([
                    authFetch('/subjects/with-stats/all').then(r => r.ok ? r.json() : []),
                    authFetch('/mcq-exams/').then(r => r.ok ? r.json() : []),
                    authFetch('/mcq-pool/').then(r => r.ok ? r.json() : []),
                    authFetch('/auth/students').then(r => r.ok ? r.json() : []),
                ]);
                if (subRes.status === 'fulfilled') setSubjects(Array.isArray(subRes.value) ? subRes.value : []);
                if (examRes.status === 'fulfilled') setExams(Array.isArray(examRes.value) ? examRes.value : []);
                if (poolRes.status === 'fulfilled') setPoolCount(poolRes.value?.total ?? (Array.isArray(poolRes.value) ? poolRes.value.length : 0));
                if (stuRes.status === 'fulfilled') setStudentCount(Array.isArray(stuRes.value) ? stuRes.value.length : 0);
            } finally {
                setLoading(false);
            }
        };
        fetchAll();
    }, []);

    // ── derived data ────────────────────────────────────────────────────────
    const liveCount = exams.filter(e => getExamStatus(e) === 'live').length;
    const upcomingCount = exams.filter(e => getExamStatus(e) === 'upcoming').length;
    const endedCount = exams.filter(e => getExamStatus(e) === 'ended').length;

    const examStatusData = [
        { name: 'Live', value: liveCount, color: '#059669' },
        { name: 'Upcoming', value: upcomingCount, color: '#0061a1' },
        { name: 'Ended', value: endedCount, color: '#D1D5DB' },
    ];

    const subjectChartData = subjects
        .slice(0, 8)
        .map(s => ({
            name: s.name.length > 14 ? s.name.slice(0, 13) + '…' : s.name,
            Docs: s.document_count || 0,
            Concepts: s.concept_count || 0,
        }));

    const recentExams = [...exams]
        .sort((a, b) => dayjs(b.created_at || b.start_time).valueOf() - dayjs(a.created_at || a.start_time).valueOf())
        .slice(0, 6);

    const totalDocs = subjects.reduce((acc, s) => acc + (s.document_count || 0), 0);
    const totalConcepts = subjects.reduce((acc, s) => acc + (s.concept_count || 0), 0);

    return (
        <div className="dash-container">
            {/* Page header */}
            <div className="dash-header">
                <div>
                    <h1 className="dash-title">Dashboard</h1>
                    <p className="dash-subtitle">Overview of your assessment platform</p>
                </div>
            </div>

            {loading ? (
                <div className="dash-loading">Loading…</div>
            ) : (
                <>
                    {/* ── Stat cards ── */}
                    <div className="dash-stats-row">
                        <StatCard icon={Library} label="Subjects" value={subjects.length} sub={`${totalDocs} docs · ${totalConcepts} concepts`} accent="#0061a1" />
                        <StatCard icon={Database} label="Pool Questions" value={poolCount} sub="MCQ question bank" accent="#0061a1" />
                        <StatCard icon={ClipboardList} label="Total Exams" value={exams.length} sub={`${liveCount} live · ${upcomingCount} upcoming`} accent="#059669" />
                        <StatCard icon={GraduationCap} label="Students" value={studentCount} sub="registered students" accent="#0061a1" />
                    </div>

                    {/* ── Charts row ── */}
                    <div className="dash-charts-row">
                        {/* Exam status breakdown */}
                        <div className="dash-card dash-chart-card">
                            <div className="dash-card-header">
                                <TrendingUp size={15} />
                                <span>Exam Status Breakdown</span>
                            </div>
                            {exams.length === 0 ? (
                                <div className="dash-empty-chart">No exams yet</div>
                            ) : (
                                <ResponsiveContainer width="100%" height={200}>
                                    <BarChart data={examStatusData} barSize={38} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                                        <Tooltip content={<ChartTooltip />} cursor={{ fill: '#F3F4F6' }} />
                                        <Bar dataKey="value" radius={[4, 4, 0, 0]} name="Exams">
                                            {examStatusData.map((entry, index) => (
                                                <Cell key={index} fill={entry.color} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                            <div className="dash-legend-row">
                                {examStatusData.map(item => (
                                    <div key={item.name} className="dash-legend-item">
                                        <span className="dash-legend-dot" style={{ background: item.color }} />
                                        <span>{item.name}</span>
                                        <strong>{item.value}</strong>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Subject document/concept chart */}
                        <div className="dash-card dash-chart-card">
                            <div className="dash-card-header">
                                <Library size={15} />
                                <span>Subject Content</span>
                            </div>
                            {subjectChartData.length === 0 ? (
                                <div className="dash-empty-chart">No subjects yet</div>
                            ) : (
                                <ResponsiveContainer width="100%" height={200}>
                                    <BarChart data={subjectChartData} barSize={14} barCategoryGap="30%" margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                        <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9CA3AF' }} axisLine={false} tickLine={false} />
                                        <Tooltip content={<ChartTooltip />} cursor={{ fill: '#F3F4F6' }} />
                                        <Bar dataKey="Docs" fill="#0061a1" radius={[3, 3, 0, 0]} />
                                        <Bar dataKey="Concepts" fill="#BFDBFE" radius={[3, 3, 0, 0]} />
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                            <div className="dash-legend-row">
                                <div className="dash-legend-item">
                                    <span className="dash-legend-dot" style={{ background: '#0061a1' }} />
                                    <span>Documents</span>
                                </div>
                                <div className="dash-legend-item">
                                    <span className="dash-legend-dot" style={{ background: '#BFDBFE' }} />
                                    <span>Concepts</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ── Recent exams table ── */}
                    <div className="dash-card dash-table-card">
                        <div className="dash-card-header">
                            <Calendar size={15} />
                            <span>Recent Exams</span>
                            <a href="/mcq-exams" className="dash-card-link">View all →</a>
                        </div>
                        {recentExams.length === 0 ? (
                            <div className="dash-empty-chart">No exams created yet</div>
                        ) : (
                            <table className="dash-table">
                                <thead>
                                    <tr>
                                        <th>Title</th>
                                        <th>Subject</th>
                                        <th>Questions</th>
                                        <th>Duration</th>
                                        <th>Start</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {recentExams.map(exam => {
                                        const st = getExamStatus(exam);
                                        return (
                                            <tr key={exam.id}>
                                                <td>
                                                    <a href={`/mcq-exams/${exam.id}`} className="dash-exam-link">
                                                        {exam.title}
                                                    </a>
                                                </td>
                                                <td className="dash-cell-muted">{exam.subject_name || '—'}</td>
                                                <td className="dash-cell-muted">{exam.total_questions}</td>
                                                <td className="dash-cell-muted">{exam.duration_minutes} min</td>
                                                <td className="dash-cell-muted">{dayjs(exam.start_time).format('MMM D, HH:mm')}</td>
                                                <td>
                                                    <span className="dash-status-badge"
                                                        style={{ background: STATUS_BG[st], color: STATUS_COLOR[st] }}>
                                                        {STATUS_LABEL[st]}
                                                    </span>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};

export default Dashboard;
