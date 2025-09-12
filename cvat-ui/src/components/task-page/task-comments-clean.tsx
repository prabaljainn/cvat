// Copyright (C) 2025 CVAT Custom Task Comments
// SPDX-License-Identifier: MIT

import './task-comments.scss';
import React from 'react';
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
    Tooltip,
} from 'antd';
import {
    CommentOutlined,
    PlusOutlined,
    ReloadOutlined,
    UserOutlined,
    ClockCircleOutlined,
    EditOutlined,
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
    is_edited: boolean;
    created_date: string;
    updated_date: string;
    reply_count: number;
}

interface CommentStats {
    total_comments: number;
    comment_types: Record<string, { count: number; display: string }>;
    recent_activity: {
        comments_last_week: number;
        comments_last_month: number;
    };
}

interface NewComment {
    message: string;
    type: string;
    parentId: number | null;
}

interface Props {
    taskId: number;
    taskName: string;
}

interface State {
    comments: TaskComment[];
    stats: CommentStats | null;
    loading: boolean;
    showCommentForm: boolean;
    newComment: NewComment;
    submitting: boolean;
}

class TaskCommentsComponent extends React.PureComponent<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = {
            comments: [],
            stats: null,
            loading: false,
            showCommentForm: false,
            newComment: { message: '', type: 'GEN', parentId: null },
            submitting: false,
        };
    }

    componentDidMount(): void {
        this.loadComments();
        this.loadStats();
    }

    private getCommentTypeColor(type: string): string {
        const colors: Record<string, string> = {
            GEN: 'blue',
            QUE: 'orange',
            ISS: 'red',
            SUG: 'green',
        };
        return colors[type] || 'default';
    }

    private async loadComments(): Promise<void> {
        const { taskId } = this.props;

        try {
            this.setState({ loading: true });

            console.log(`Loading comments for task ${taskId}...`);

            const response = await core.server.request(
                `/api/custom/tasks/${taskId}/comments/`,
                {
                    method: 'GET',
                }
            );

            console.log('Comments response:', response);

            // Get data from Axios response
            const data = response.data;
            console.log('Comments data:', data);

            this.setState({
                comments: data.results || [],
                loading: false,
            });
        } catch (error) {
            console.error('Error loading comments:', error);
            notification.error({
                message: 'Failed to load comments',
                description: 'Could not retrieve task comments. Please try again.',
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
                    method: 'GET',
                }
            );

            // Get data from Axios response
            const stats = response.data;
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
                description: 'Please enter a comment message.',
            });
            return;
        }

        try {
            this.setState({ submitting: true });

            const commentData = {
                task: taskId,
                message: newComment.message.trim(),
                comment_type: newComment.type,
                ...(newComment.parentId && { parent_comment: newComment.parentId }),
            };

            const response = await core.server.request(
                '/api/custom/task-comments/create/',
                {
                    method: 'POST',
                    data: commentData,
                }
            );

            console.log('Create comment response:', response);

            notification.success({
                message: 'Comment Added',
                description: 'Your comment has been added successfully.',
            });

            // Reset form and reload comments
            this.setState({
                newComment: { message: '', type: 'GEN', parentId: null },
                showCommentForm: false,
                submitting: false,
            });

            await this.loadComments();
            await this.loadStats();
        } catch (error) {
            console.error('Error creating comment:', error);
            notification.error({
                message: 'Failed to create comment',
                description: 'Could not create comment. Please try again.',
            });
            this.setState({ submitting: false });
        }
    }

    private renderCommentForm(): JSX.Element | null {
        const { showCommentForm, newComment, submitting } = this.state;

        if (!showCommentForm) return null;

        return (
            <Card size='small' style={{ marginBottom: 16 }}>
                <Space direction='vertical' style={{ width: '100%' }}>
                    <Select
                        value={newComment.type}
                        onChange={(value) => this.setState({
                            newComment: { ...newComment, type: value },
                        })}
                        style={{ width: 200 }}
                    >
                        <Option value='GEN'>General</Option>
                        <Option value='QUE'>Question</Option>
                        <Option value='ISS'>Issue</Option>
                        <Option value='SUG'>Suggestion</Option>
                    </Select>

                    <TextArea
                        value={newComment.message}
                        onChange={(e) => this.setState({
                            newComment: { ...newComment, message: e.target.value },
                        })}
                        placeholder={
                            newComment.parentId
                                ? 'Write a reply...'
                                : 'Write a comment...'
                        }
                        rows={4}
                        maxLength={1000}
                        showCount
                    />

                    <Space>
                        <Button
                            type='primary'
                            loading={submitting}
                            onClick={() => this.createComment()}
                        >
                            {newComment.parentId ? 'Reply' : 'Add Comment'}
                        </Button>
                        <Button
                            onClick={() => this.setState({
                                showCommentForm: false,
                                newComment: { message: '', type: 'GEN', parentId: null },
                            })}
                        >
                            Cancel
                        </Button>
                    </Space>
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
                            size='small'
                            icon={<UserOutlined />}
                            style={{ backgroundColor: '#1890ff' }}
                        />
                    }
                    title={(
                        <Space>
                            <Text strong>{authorName}</Text>
                            <Tag
                                color={this.getCommentTypeColor(comment.comment_type)}
                            >
                                {comment.comment_type_display}
                            </Tag>
                            {comment.is_reply && (
                                <Tag color='default'>
                                    Reply
                                </Tag>
                            )}
                            {comment.is_edited && (
                                <Tooltip title='This comment has been edited'>
                                    <EditOutlined style={{ color: '#999', fontSize: '12px' }} />
                                </Tooltip>
                            )}
                        </Space>
                    )}
                    description={(
                        <Space>
                            <ClockCircleOutlined />
                            <Text type='secondary'>
                                {moment(comment.created_date).format('MMM DD, YYYY HH:mm')}
                            </Text>
                            {!comment.is_reply && comment.reply_count > 0 && (
                                <Text type='secondary'>
                                    {comment.reply_count} {comment.reply_count === 1 ? 'reply' : 'replies'}
                                </Text>
                            )}
                        </Space>
                    )}
                />
                <div style={{ marginLeft: 40 }}>
                    <Paragraph style={{ marginBottom: 8 }}>
                        {comment.message}
                    </Paragraph>
                    {!comment.is_reply && (
                        <Button
                            type='link'
                            size='small'
                            icon={<CommentOutlined />}
                            onClick={() => this.setState({
                                showCommentForm: true,
                                newComment: {
                                    message: '',
                                    type: 'GEN',
                                    parentId: comment.id,
                                },
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
            <Card size='small' style={{ marginBottom: 16 }}>
                <Space split={<Divider type='vertical' />}>
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
                                >
                                    {data.display}: {data.count}
                                </Tag>
                            )
                        ))}
                    </Space>
                </Space>
            </Card>
        );
    }

    public render(): JSX.Element {
        const { comments, loading, showCommentForm } = this.state;

        // Group comments by thread (parent comments with their replies)
        const parentComments = comments.filter((c) => !c.is_reply);
        const replies = comments.filter((c) => c.is_reply);

        const threaded = parentComments.map((parent) => ({
            ...parent,
            replies: replies.filter((r) => r.parent_comment === parent.id),
        }));

        return (
            <div className='cvat-task-comments'>
                <Card
                    title={(
                        <Space>
                            <CommentOutlined />
                            <span>Task Comments</span>
                        </Space>
                    )}
                    extra={(
                        <Space>
                            <Button
                                size='small'
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
                                    type='primary'
                                    size='small'
                                    icon={<PlusOutlined />}
                                    onClick={() => this.setState({ showCommentForm: true })}
                                >
                                    Add Comment
                                </Button>
                            )}
                        </Space>
                    )}
                    style={{ marginTop: 16 }}
                >
                    {this.renderStats()}
                    {this.renderCommentForm()}

                    <Spin spinning={loading}>
                        {threaded.length > 0 ? (
                            <List
                                dataSource={threaded}
                                renderItem={(comment) => (
                                    <div key={comment.id}>
                                        {this.renderComment(comment)}
                                        {comment.replies.map((reply) => (
                                            <div key={reply.id} style={{ marginLeft: 40 }}>
                                                {this.renderComment(reply)}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            />
                        ) : (
                            <Empty
                                description='No comments yet'
                                image={Empty.PRESENTED_IMAGE_SIMPLE}
                            >
                                <Button
                                    type='primary'
                                    icon={<PlusOutlined />}
                                    onClick={() => this.setState({ showCommentForm: true })}
                                >
                                    Add First Comment
                                </Button>
                            </Empty>
                        )}
                    </Spin>
                </Card>
            </div>
        );
    }
}

export default TaskCommentsComponent;
