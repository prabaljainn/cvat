// Copyright (C) 2025 CVAT Custom Task Comments
// SPDX-License-Identifier: MIT

import './task-comments.scss';
import React, { useState, useEffect } from 'react';
import { connect } from 'react-redux';
import {
    Card,
    List,
    Avatar,
    Button,
    Input,
    Select,
    Space,
    Typography,
    Tag,
    Divider,
    notification,
    Spin,
    Empty,
    Tooltip
} from 'antd';
import {
    CommentOutlined,
    PlusOutlined,
    ReloadOutlined,
    UserOutlined,
    ClockCircleOutlined,
    EditOutlined
} from '@ant-design/icons';
import moment from 'moment';

import { getCore } from 'cvat-core-wrapper';

const { TextArea } = Input;
const { Option } = Select;
const { Text, Paragraph } = Typography;

const core = getCore();

interface TaskComment {
    id: number;
    task: number;
    author: {
        id: number;
        username: string;
        first_name: string;
        last_name: string;
    };
    message: string;
    comment_type: string;
    comment_type_display: string;
    parent_comment: number | null;
    is_reply: boolean;
    reply_count: number;
    created_date: string;
    updated_date: string;
    is_edited: boolean;
}

interface TaskCommentsStats {
    total_comments: number;
    comment_types: Record<string, { name: string; count: number }>;
    recent_activity: {
        comments_last_week: number;
    };
}

interface Props {
    taskId: number;
    taskName: string;
}

interface State {
    comments: TaskComment[];
    stats: TaskCommentsStats | null;
    loading: boolean;
    submitting: boolean;
    showCommentForm: boolean;
    newComment: {
        message: string;
        type: string;
        parentId: number | null;
    };
}

const COMMENT_TYPES = [
    { value: 'GEN', label: 'General', color: 'blue' },
    { value: 'FB', label: 'Feedback', color: 'green' },
    { value: 'ISS', label: 'Issue', color: 'red' },
    { value: 'REV', label: 'Review', color: 'orange' },
    { value: 'NOTE', label: 'Note', color: 'purple' },
    { value: 'Q', label: 'Question', color: 'cyan' }
];

class TaskCommentsComponent extends React.PureComponent<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = {
            comments: [],
            stats: null,
            loading: true,
            submitting: false,
            showCommentForm: false,
            newComment: {
                message: '',
                type: 'GEN',
                parentId: null
            }
        };
    }

    public componentDidMount(): void {
        this.loadComments();
        this.loadStats();
    }

    private async loadComments(): Promise<void> {
        const { taskId } = this.props;

        try {
            this.setState({ loading: true });

            console.log(`Loading comments for task ${taskId}...`);

            const response = await core.server.request(
                `/api/custom/tasks/${taskId}/comments/`,
                {
                    method: 'GET'
                }
            );

            console.log('Comments response:', response);

            // Parse the response data
            const data = await response.json();
            console.log('Comments data:', data);

            this.setState({
                comments: data.results || [],
                loading: false
            });

        } catch (error) {
            console.error('Error loading comments:', error);
            notification.error({
                message: 'Failed to load comments',
                description: 'Could not retrieve task comments. Please try again.'
            });
            this.setState({ loading: false });
        }
    }

    private async loadStats(): Promise<void> {
        const { taskId } = this.props;

        try {
            const response = await core.server.request(
                `/api/custom/task-comments/stats/?task_id=${taskId}`,
                {
                    method: 'GET'
                }
            );

            // Parse the response data
            const stats = await response.json();
            this.setState({ stats });

        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    private async createComment(): Promise<void> {
        const { taskId } = this.props;
        const { newComment } = this.state;

        if (!newComment.message.trim()) {
            notification.warning({
                message: 'Empty Comment',
                description: 'Please enter a comment message.'
            });
            return;
        }

        try {
            this.setState({ submitting: true });

            const commentData = {
                task: taskId,
                message: newComment.message.trim(),
                comment_type: newComment.type,
                ...(newComment.parentId && { parent_comment: newComment.parentId })
            };

            const response = await core.server.request(
                '/api/custom/task-comments/create/',
                {
                    method: 'POST',
                    data: commentData
                }
            );

            notification.success({
                message: 'Comment Added',
                description: 'Your comment has been added successfully.'
            });

            // Reset form and reload comments
            this.setState({
                newComment: { message: '', type: 'GEN', parentId: null },
                showCommentForm: false,
                submitting: false
            });

            await this.loadComments();
            await this.loadStats();

        } catch (error) {
            console.error('Error creating comment:', error);
            notification.error({
                message: 'Failed to Add Comment',
                description: 'Could not add your comment. Please try again.'
            });
            this.setState({ submitting: false });
        }
    }

    private getCommentTypeColor(type: string): string {
        const commentType = COMMENT_TYPES.find(t => t.value === type);
        return commentType?.color || 'default';
    }

    private formatDate(dateString: string): string {
        return moment(dateString).format('MMM DD, YYYY HH:mm');
    }

    private renderCommentForm(): JSX.Element {
        const { newComment, submitting } = this.state;

        return (
            <Card
                size="small"
                title="Add Comment"
                style={{ marginBottom: 16 }}
                extra={
                    <Button
                        size="small"
                        onClick={() => this.setState({ showCommentForm: false })}
                    >
                        Cancel
                    </Button>
                }
            >
                <Space direction="vertical" style={{ width: '100%' }}>
                    <Select
                        value={newComment.type}
                        onChange={(type) => this.setState({
                            newComment: { ...newComment, type }
                        })}
                        style={{ width: 120 }}
                        size="small"
                    >
                        {COMMENT_TYPES.map(type => (
                            <Option key={type.value} value={type.value}>
                                <Tag color={type.color} style={{ margin: 0 }}>
                                    {type.label}
                                </Tag>
                            </Option>
                        ))}
                    </Select>

                    <TextArea
                        value={newComment.message}
                        onChange={(e) => this.setState({
                            newComment: { ...newComment, message: e.target.value }
                        })}
                        placeholder="Enter your comment..."
                        rows={3}
                        maxLength={1000}
                        showCount
                    />

                    <div style={{ textAlign: 'right' }}>
                        <Button
                            type="primary"
                            size="small"
                            loading={submitting}
                            onClick={() => this.createComment()}
                            disabled={!newComment.message.trim()}
                        >
                            Add Comment
                        </Button>
                    </div>
                </Space>
            </Card>
        );
    }

    private renderComment(comment: TaskComment): JSX.Element {
        const authorName = comment.author.first_name && comment.author.last_name
            ? `${comment.author.first_name} ${comment.author.last_name}`
            : comment.author.username;

        return (
            <List.Item key={comment.id}>
                <List.Item.Meta
                    avatar={
                        <Avatar
                            size="small"
                            icon={<UserOutlined />}
                            style={{ backgroundColor: '#1890ff' }}
                        >
                            {authorName.charAt(0).toUpperCase()}
                        </Avatar>
                    }
                    title={
                        <Space>
                            <Text strong>{authorName}</Text>
                            <Tag
                                color={this.getCommentTypeColor(comment.comment_type)}
                                size="small"
                            >
                                {comment.comment_type_display}
                            </Tag>
                            {comment.is_reply && (
                                <Tag size="small" color="default">
                                    Reply
                                </Tag>
                            )}
                            {comment.is_edited && (
                                <Tooltip title="This comment has been edited">
                                    <EditOutlined style={{ color: '#999', fontSize: '12px' }} />
                                </Tooltip>
                            )}
                        </Space>
                    }
                    description={
                        <Space>
                            <ClockCircleOutlined />
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                                {this.formatDate(comment.created_date)}
                            </Text>
                            {comment.reply_count > 0 && (
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    • {comment.reply_count} {comment.reply_count === 1 ? 'reply' : 'replies'}
                                </Text>
                            )}
                        </Space>
                    }
                />
                <div style={{ marginLeft: 40 }}>
                    <Paragraph style={{ marginBottom: 8 }}>
                        {comment.message}
                    </Paragraph>
                    {!comment.is_reply && (
                        <Button
                            type="link"
                            size="small"
                            icon={<CommentOutlined />}
                            onClick={() => this.setState({
                                showCommentForm: true,
                                newComment: {
                                    message: '',
                                    type: 'GEN',
                                    parentId: comment.id
                                }
                            })}
                            style={{ padding: 0, height: 'auto' }}
                        >
                            Reply
                        </Button>
                    )}
                </div>
            </List.Item>
        );
    }

    private renderStats(): JSX.Element | null {
        const { stats } = this.state;

        if (!stats) return null;

        return (
            <Card size="small" style={{ marginBottom: 16 }}>
                <Space split={<Divider type="vertical" />}>
                    <Text>
                        <strong>{stats.total_comments}</strong> Total Comments
                    </Text>
                    <Text>
                        <strong>{stats.recent_activity.comments_last_week}</strong> This Week
                    </Text>
                    <Space>
                        {Object.entries(stats.comment_types).map(([type, data]) => (
                            data.count > 0 && (
                                <Tag
                                    key={type}
                                    color={this.getCommentTypeColor(type)}
                                    style={{ margin: 0 }}
                                >
                                    {data.name}: {data.count}
                                </Tag>
                            )
                        ))}
                    </Space>
                </Space>
            </Card>
        );
    }

    public render(): JSX.Element {
        const { taskName } = this.props;
        const { comments, loading, showCommentForm } = this.state;

        // Group comments by thread (parent comments with their replies)
        const parentComments = comments.filter(c => !c.is_reply);
        const replies = comments.filter(c => c.is_reply);

        const threaded = parentComments.map(parent => ({
            ...parent,
            replies: replies.filter(r => r.parent_comment === parent.id)
        }));

        return (
            <div className="cvat-task-comments">
                <Card
                    title={
                        <Space>
                            <CommentOutlined />
                            <span>Task Comments</span>
                        </Space>
                    }
                    extra={
                        <Space>
                            <Button
                                size="small"
                                icon={<ReloadOutlined />}
                                onClick={() => {
                                    this.loadComments();
                                    this.loadStats();
                                }}
                            >
                                Refresh
                            </Button>
                            {!showCommentForm && (
                                <Button
                                    type="primary"
                                    size="small"
                                    icon={<PlusOutlined />}
                                    onClick={() => this.setState({ showCommentForm: true })}
                                >
                                    Add Comment
                                </Button>
                            )}
                        </Space>
                    }
                    style={{ marginTop: 16 }}
                >
                    {this.renderStats()}

                    {showCommentForm && this.renderCommentForm()}

                    <Spin spinning={loading}>
                        {comments.length === 0 && !loading ? (
                            <Empty
                                description="No comments yet"
                                image={Empty.PRESENTED_IMAGE_SIMPLE}
                            >
                                <Button
                                    type="primary"
                                    onClick={() => this.setState({ showCommentForm: true })}
                                >
                                    Add First Comment
                                </Button>
                            </Empty>
                        ) : (
                            <List
                                itemLayout="vertical"
                                dataSource={threaded}
                                renderItem={(comment) => (
                                    <div key={comment.id}>
                                        {this.renderComment(comment)}
                                        {comment.replies && comment.replies.length > 0 && (
                                            <div style={{ marginLeft: 40, paddingLeft: 16, borderLeft: '2px solid #f0f0f0' }}>
                                                {comment.replies.map(reply => this.renderComment(reply))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            />
                        )}
                    </Spin>
                </Card>
            </div>
        );
    }
}

export default TaskCommentsComponent;
