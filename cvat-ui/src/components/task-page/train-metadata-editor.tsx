// Copyright (C) 2025 CVAT Custom Train Metadata Component
// SPDX-License-Identifier: MIT

import React, { useState, useEffect } from 'react';
import { Row, Col, Input, Select, InputNumber, Button, message, Spin } from 'antd';
import Text from 'antd/lib/typography/Text';
import Title from 'antd/lib/typography/Title';
import { EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import { getCore } from 'cvat-core-wrapper';

const { Option } = Select;
const { TextArea } = Input;

interface TrainMetadata {
    train_id: string;
    verdict: 'AC' | 'NA' | 'RJ';
    verdict_display: string;
    notes: string | null;
    confidence_score: number | null;
    created_date: string;
    updated_date: string;
}

interface TrainMetadataEditorProps {
    taskId: number;
    taskName: string;
}

const TrainMetadataEditor: React.FC<TrainMetadataEditorProps> = ({ taskId, taskName }) => {
    const [metadata, setMetadata] = useState<TrainMetadata | null>(null);
    const [loading, setLoading] = useState(false);
    const [editing, setEditing] = useState(false);
    const [editData, setEditData] = useState<Partial<TrainMetadata>>({});

    const core = getCore();

    // Fetch train metadata
    const fetchMetadata = async () => {
        setLoading(true);
        try {
            const response = await core.server.request(`/api/custom/tasks/${taskId}/train-metadata/`, {
                method: 'GET',
            });

            if (response.status === 200) {
                const data = response.data;
                setMetadata({
                    train_id: data.train_id,
                    verdict: data.verdict,
                    verdict_display: data.verdict_display,
                    notes: data.notes,
                    confidence_score: data.confidence_score,
                    created_date: data.created_date,
                    updated_date: data.updated_date,
                });
            } else {
                message.error('Failed to load train metadata');
            }
        } catch (error) {
            console.error('Error fetching train metadata:', error);
            message.error('Error loading train metadata');
        } finally {
            setLoading(false);
        }
    };

    // Update train metadata
    const updateMetadata = async () => {
        setLoading(true);
        try {
            const response = await core.server.request(`/api/custom/tasks/${taskId}/train-metadata/`, {
                method: 'PATCH',
                data: editData,
            });

            if (response.status === 200) {
                const data = response.data;
                setMetadata({
                    train_id: data.train_id,
                    verdict: data.verdict,
                    verdict_display: data.verdict_display,
                    notes: data.notes,
                    confidence_score: data.confidence_score,
                    created_date: metadata?.created_date || '',
                    updated_date: data.updated_date,
                });
                setEditing(false);
                setEditData({});
                message.success('Train metadata updated successfully');
            } else {
                message.error(`Failed to update: ${response.data?.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error updating train metadata:', error);
            message.error('Error updating train metadata');
        } finally {
            setLoading(false);
        }
    };

    // Quick verdict update
    const updateVerdict = async (verdict: 'AC' | 'NA' | 'RJ') => {
        setLoading(true);
        try {
            const response = await core.server.request(`/api/custom/tasks/${taskId}/verdict/`, {
                method: 'PATCH',
                data: { verdict },
            });

            if (response.status === 200) {
                const data = response.data;
                setMetadata(prev => prev ? {
                    ...prev,
                    verdict: data.new_verdict,
                    verdict_display: data.verdict_display,
                    updated_date: data.updated_date,
                } : null);
                message.success(`Verdict updated to ${data.verdict_display}`);
            } else {
                message.error(`Failed to update verdict: ${response.data?.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error updating verdict:', error);
            message.error('Error updating verdict');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchMetadata();
    }, [taskId]);

    const startEditing = () => {
        setEditing(true);
        setEditData({
            train_id: metadata?.train_id || '',
            verdict: metadata?.verdict || 'NA',
            notes: metadata?.notes || '',
            confidence_score: metadata?.confidence_score || null,
        });
    };

    const cancelEditing = () => {
        setEditing(false);
        setEditData({});
    };

    const getVerdictColor = (verdict: string) => {
        switch (verdict) {
            case 'AC': return '#52c41a'; // Green
            case 'RJ': return '#ff4d4f'; // Red
            case 'NA': return '#faad14'; // Orange
            default: return '#d9d9d9'; // Gray
        }
    };

    if (loading && !metadata) {
        return (
            <div style={{ textAlign: 'center', padding: '20px' }}>
                <Spin size="large" />
                <div>Loading train metadata...</div>
            </div>
        );
    }

    if (!metadata) {
        return (
            <div style={{ padding: '16px', border: '1px solid #d9d9d9', borderRadius: '6px', marginBottom: '16px' }}>
                <Text type="secondary">No train metadata available</Text>
            </div>
        );
    }

    return (
        <div style={{ padding: '16px', border: '1px solid #d9d9d9', borderRadius: '6px', marginBottom: '16px' }}>
            <Row justify="space-between" align="middle" style={{ marginBottom: '12px' }}>
                <Col>
                    <Title level={5} style={{ margin: 0 }}>🚂 Train Metadata</Title>
                </Col>
                <Col>
                    {!editing && (
                        <Button
                            type="link"
                            icon={<EditOutlined />}
                            onClick={startEditing}
                            disabled={loading}
                        >
                            Edit
                        </Button>
                    )}
                </Col>
            </Row>

            <Spin spinning={loading}>
                {editing ? (
                    // Edit mode
                    <div>
                        <Row gutter={[16, 8]}>
                            <Col span={12}>
                                <Text strong>Train ID:</Text>
                                <Input
                                    value={editData.train_id}
                                    onChange={(e) => setEditData(prev => ({ ...prev, train_id: e.target.value }))}
                                    placeholder="Enter train ID"
                                />
                            </Col>
                            <Col span={12}>
                                <Text strong>Verdict:</Text>
                                <Select
                                    value={editData.verdict}
                                    onChange={(value) => setEditData(prev => ({ ...prev, verdict: value }))}
                                    style={{ width: '100%' }}
                                >
                                    <Option value="AC">✅ Accepted</Option>
                                    <Option value="NA">⚪ Not Applicable</Option>
                                    <Option value="RJ">❌ Rejected</Option>
                                </Select>
                            </Col>
                        </Row>
                        <Row gutter={[16, 8]} style={{ marginTop: '8px' }}>
                            <Col span={12}>
                                <Text strong>Confidence Score:</Text>
                                <InputNumber
                                    value={editData.confidence_score}
                                    onChange={(value) => setEditData(prev => ({ ...prev, confidence_score: value }))}
                                    min={0}
                                    max={1}
                                    step={0.01}
                                    style={{ width: '100%' }}
                                    placeholder="0.0 - 1.0"
                                />
                            </Col>
                            <Col span={12}>
                                <div style={{ paddingTop: '24px' }}>
                                    <Button
                                        type="primary"
                                        icon={<SaveOutlined />}
                                        onClick={updateMetadata}
                                        style={{ marginRight: '8px' }}
                                    >
                                        Save
                                    </Button>
                                    <Button
                                        icon={<CloseOutlined />}
                                        onClick={cancelEditing}
                                    >
                                        Cancel
                                    </Button>
                                </div>
                            </Col>
                        </Row>
                        <Row style={{ marginTop: '8px' }}>
                            <Col span={24}>
                                <Text strong>Notes:</Text>
                                <TextArea
                                    value={editData.notes || ''}
                                    onChange={(e) => setEditData(prev => ({ ...prev, notes: e.target.value }))}
                                    placeholder="Optional notes about the train event"
                                    rows={3}
                                />
                            </Col>
                        </Row>
                    </div>
                ) : (
                    // View mode
                    <div>
                        <Row gutter={[16, 8]}>
                            <Col span={12}>
                                <Text strong>Train ID: </Text>
                                <Text code>{metadata.train_id}</Text>
                            </Col>
                            <Col span={12}>
                                <Text strong>Verdict: </Text>
                                <span style={{
                                    color: getVerdictColor(metadata.verdict),
                                    fontWeight: 'bold'
                                }}>
                                    {metadata.verdict_display}
                                </span>
                                <div style={{ marginTop: '4px' }}>
                                    <Button size="small" onClick={() => updateVerdict('AC')} disabled={metadata.verdict === 'AC'}>
                                        ✅ Accept
                                    </Button>
                                    <Button size="small" onClick={() => updateVerdict('NA')} disabled={metadata.verdict === 'NA'} style={{ margin: '0 4px' }}>
                                        ⚪ N/A
                                    </Button>
                                    <Button size="small" onClick={() => updateVerdict('RJ')} disabled={metadata.verdict === 'RJ'}>
                                        ❌ Reject
                                    </Button>
                                </div>
                            </Col>
                        </Row>
                        {(metadata.confidence_score !== null || metadata.notes) && (
                            <Row gutter={[16, 8]} style={{ marginTop: '8px' }}>
                                {metadata.confidence_score !== null && (
                                    <Col span={12}>
                                        <Text strong>Confidence: </Text>
                                        <Text>{(metadata.confidence_score * 100).toFixed(1)}%</Text>
                                    </Col>
                                )}
                                {metadata.notes && (
                                    <Col span={metadata.confidence_score !== null ? 12 : 24}>
                                        <Text strong>Notes: </Text>
                                        <Text>{metadata.notes}</Text>
                                    </Col>
                                )}
                            </Row>
                        )}
                        <Row style={{ marginTop: '8px' }}>
                            <Col span={24}>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    Updated: {new Date(metadata.updated_date).toLocaleString()}
                                </Text>
                            </Col>
                        </Row>
                    </div>
                )}
            </Spin>
        </div>
    );
};

export default TrainMetadataEditor;
