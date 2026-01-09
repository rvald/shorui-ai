/**
 * Agent Chat View Component
 *
 * Displays agent conversation with step visualization (Thought → Action → Observation).
 */

import { Button } from "@/components/ui/button";
import { useState, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
    Loader2,
    Copy,
    CopyCheck,
    ChevronDown,
    ChevronRight,
    Brain,
    Wrench,
    Eye,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { InputForm } from "@/components/InputForm";
import type { Message } from "@langchain/langgraph-sdk";
import type { AgentStep } from "@/api/agentApi";

// Markdown component props type
type MdComponentProps = {
    className?: string;
    children?: ReactNode;
    [key: string]: any;
};

// Markdown components
const mdComponents = {
    h1: ({ className, children, ...props }: MdComponentProps) => (
        <h1 className={cn("text-2xl font-bold mt-4 mb-2", className)} {...props}>
            {children}
        </h1>
    ),
    h2: ({ className, children, ...props }: MdComponentProps) => (
        <h2 className={cn("text-xl font-bold mt-3 mb-2", className)} {...props}>
            {children}
        </h2>
    ),
    h3: ({ className, children, ...props }: MdComponentProps) => (
        <h3 className={cn("text-lg font-bold mt-3 mb-1", className)} {...props}>
            {children}
        </h3>
    ),
    p: ({ className, children, ...props }: MdComponentProps) => (
        <p className={cn("mb-3 leading-7", className)} {...props}>
            {children}
        </p>
    ),
    ul: ({ className, children, ...props }: MdComponentProps) => (
        <ul className={cn("list-disc pl-6 mb-3", className)} {...props}>
            {children}
        </ul>
    ),
    ol: ({ className, children, ...props }: MdComponentProps) => (
        <ol className={cn("list-decimal pl-6 mb-3", className)} {...props}>
            {children}
        </ol>
    ),
    li: ({ className, children, ...props }: MdComponentProps) => (
        <li className={cn("mb-1", className)} {...props}>
            {children}
        </li>
    ),
    code: ({ className, children, ...props }: MdComponentProps) => (
        <code
            className={cn(
                "bg-neutral-900 rounded px-1 py-0.5 font-mono text-xs",
                className
            )}
            {...props}
        >
            {children}
        </code>
    ),
    pre: ({ className, children, ...props }: MdComponentProps) => (
        <pre
            className={cn(
                "bg-neutral-900 p-3 rounded-lg overflow-x-auto font-mono text-xs my-3",
                className
            )}
            {...props}
        >
            {children}
        </pre>
    ),
};

// Agent Step Component
interface AgentStepViewProps {
    step: AgentStep;
    isExpanded: boolean;
    onToggle: () => void;
}

function AgentStepView({ step, isExpanded, onToggle }: AgentStepViewProps) {
    return (
        <div className="border border-neutral-700 rounded-lg mb-2 overflow-hidden">
            <button
                onClick={onToggle}
                className="w-full flex items-center gap-2 p-2 hover:bg-neutral-700/50 transition-colors text-left"
            >
                {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-neutral-400" />
                ) : (
                    <ChevronRight className="h-4 w-4 text-neutral-400" />
                )}
                <span className="text-sm font-medium text-neutral-300">
                    Step {step.step_number}
                </span>
                {step.action && (
                    <Badge variant="secondary" className="text-xs">
                        {step.action}
                    </Badge>
                )}
            </button>

            {isExpanded && (
                <div className="p-3 border-t border-neutral-700 space-y-2 bg-neutral-800/50">
                    {step.thought && (
                        <div className="flex gap-2">
                            <Brain className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
                            <div>
                                <span className="text-xs text-purple-400 font-medium">
                                    Thought
                                </span>
                                <p className="text-sm text-neutral-300 mt-1">{step.thought}</p>
                            </div>
                        </div>
                    )}
                    {step.action && (
                        <div className="flex gap-2">
                            <Wrench className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
                            <div>
                                <span className="text-xs text-blue-400 font-medium">
                                    Action
                                </span>
                                <p className="text-sm text-neutral-300 mt-1 font-mono">
                                    {step.action}
                                </p>
                            </div>
                        </div>
                    )}
                    {step.observation && (
                        <div className="flex gap-2">
                            <Eye className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <div>
                                <span className="text-xs text-green-400 font-medium">
                                    Observation
                                </span>
                                <p className="text-sm text-neutral-300 mt-1">
                                    {step.observation.length > 200
                                        ? step.observation.substring(0, 200) + "..."
                                        : step.observation}
                                </p>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// Human Message Bubble
interface HumanMessageBubbleProps {
    message: Message;
}

function HumanMessageBubble({ message }: HumanMessageBubbleProps) {
    const content =
        typeof message.content === "string"
            ? message.content
            : JSON.stringify(message.content);

    return (
        <div className="text-white rounded-3xl break-words min-h-7 bg-neutral-700 max-w-[100%] sm:max-w-[90%] px-4 pt-3 pb-3 rounded-br-lg">
            <ReactMarkdown components={mdComponents}>{content}</ReactMarkdown>
        </div>
    );
}

// AI Message Bubble with Steps
interface AiMessageBubbleProps {
    message: Message;
    steps?: AgentStep[];
    handleCopy: (text: string, messageId: string) => void;
    copiedMessageId: string | null;
}

function AiMessageBubble({
    message,
    steps,
    handleCopy,
    copiedMessageId,
}: AiMessageBubbleProps) {
    const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

    const toggleStep = (stepNum: number) => {
        setExpandedSteps((prev) => {
            const next = new Set(prev);
            if (next.has(stepNum)) {
                next.delete(stepNum);
            } else {
                next.add(stepNum);
            }
            return next;
        });
    };

    // Get the base content from message
    const messageContent =
        typeof message.content === "string"
            ? message.content
            : JSON.stringify(message.content);

    // Check if any step's observation contains a formatted compliance report
    // If so, use that rich Markdown instead of the agent's summary
    let displayContent = messageContent;
    if (steps && steps.length > 0) {
        // Find the first step with a Markdown compliance report
        const reportStep = steps.find(
            (step) =>
                step.observation &&
                (step.observation.startsWith("## 🩺") ||
                    step.observation.includes("### Executive Summary"))
        );
        if (reportStep?.observation) {
            displayContent = reportStep.observation;
        }
    }

    return (
        <div className="relative break-words flex flex-col w-full">
            {/* Agent Steps (collapsible) */}
            {steps && steps.length > 0 && (
                <div className="mb-3">
                    <div className="text-xs text-neutral-500 mb-2">
                        Agent reasoning ({steps.length} steps)
                    </div>
                    {steps.map((step) => (
                        <AgentStepView
                            key={step.step_number}
                            step={step}
                            isExpanded={expandedSteps.has(step.step_number)}
                            onToggle={() => toggleStep(step.step_number)}
                        />
                    ))}
                </div>
            )}

            {/* Final Answer - displays formatted report if available */}
            <div className="bg-neutral-800/30 rounded-lg p-3 border border-neutral-700">
                <div className="text-xs text-neutral-500 mb-2">
                    {displayContent !== messageContent ? "Compliance Report" : "Final Answer"}
                </div>
                <ReactMarkdown components={mdComponents}>{displayContent}</ReactMarkdown>
            </div>

            <Button
                variant="default"
                className={`cursor-pointer bg-neutral-700 border-neutral-600 text-neutral-300 self-end mt-2 ${displayContent.length > 0 ? "visible" : "hidden"
                    }`}
                onClick={() => handleCopy(displayContent, message.id!)}
            >
                {copiedMessageId === message.id ? "Copied" : "Copy"}
                {copiedMessageId === message.id ? <CopyCheck /> : <Copy />}
            </Button>
        </div>
    );
}

// Main Component
interface AgentChatViewProps {
    messages: Message[];
    isLoading: boolean;
    scrollAreaRef: React.RefObject<HTMLDivElement | null>;
    onSubmit: (inputValue: string, files: File[]) => void;
    onCancel: () => void;
}

export function AgentChatView({
    messages,
    isLoading,
    scrollAreaRef,
    onSubmit,
    onCancel,
}: AgentChatViewProps) {
    const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

    const handleCopy = async (text: string, messageId: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopiedMessageId(messageId);
            setTimeout(() => setCopiedMessageId(null), 2000);
        } catch (err) {
            console.error("Failed to copy text: ", err);
        }
    };

    return (
        <div className="flex flex-col h-full">
            <ScrollArea className="flex-1 overflow-y-auto" ref={scrollAreaRef}>
                <div className="p-4 md:p-6 space-y-4 max-w-4xl mx-auto pt-16">
                    {messages.map((message, index) => {
                        const steps = (message as any).additional_kwargs?.steps as
                            | AgentStep[]
                            | undefined;

                        return (
                            <div key={message.id || `msg-${index}`} className="space-y-3">
                                <div
                                    className={`flex items-start gap-3 ${message.type === "human" ? "justify-end" : ""
                                        }`}
                                >
                                    {message.type === "human" ? (
                                        <HumanMessageBubble message={message} />
                                    ) : (
                                        <AiMessageBubble
                                            message={message}
                                            steps={steps}
                                            handleCopy={handleCopy}
                                            copiedMessageId={copiedMessageId}
                                        />
                                    )}
                                </div>
                            </div>
                        );
                    })}

                    {/* Loading state */}
                    {isLoading &&
                        (messages.length === 0 ||
                            messages[messages.length - 1].type === "human") && (
                            <div className="flex items-start gap-3 mt-3">
                                <div className="relative group max-w-[85%] md:max-w-[80%] rounded-xl p-3 shadow-sm break-words bg-neutral-800 text-neutral-100 rounded-bl-none w-full min-h-[56px]">
                                    <div className="flex items-center justify-start h-full">
                                        <Loader2 className="h-5 w-5 animate-spin text-neutral-400 mr-2" />
                                        <span>Agent is reasoning...</span>
                                    </div>
                                </div>
                            </div>
                        )}
                </div>
            </ScrollArea>

            <InputForm onSubmit={onSubmit} isLoading={isLoading} onCancel={onCancel} />
        </div>
    );
}
