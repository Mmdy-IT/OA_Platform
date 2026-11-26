import {
  AlignCenterOutlined,
  AlignLeftOutlined,
  AlignRightOutlined,
  BoldOutlined,
  ClearOutlined,
  DeleteOutlined,
  FontColorsOutlined,
  FontSizeOutlined,
  ItalicOutlined,
  MergeCellsOutlined,
  OrderedListOutlined,
  RedoOutlined,
  SplitCellsOutlined,
  StrikethroughOutlined,
  TableOutlined,
  UnderlineOutlined,
  UndoOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Button, Divider, InputNumber, Popover, Select, Tooltip } from "antd";
import { Extension } from "@tiptap/core";
import Color from "@tiptap/extension-color";
import FontFamily from "@tiptap/extension-font-family";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Table from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import TextAlign from "@tiptap/extension-text-align";
import TextStyle from "@tiptap/extension-text-style";
import Underline from "@tiptap/extension-underline";
import { useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { sanitizeRichHtml, toEditorHtml } from "../richtext";

const FONT_SIZES = [
  { value: "9pt", label: "9 pt" },
  { value: "10.5pt", label: "10.5 pt" },
  { value: "12pt", label: "12 pt" },
  { value: "14pt", label: "14 pt" },
  { value: "16pt", label: "16 pt" },
  { value: "18pt", label: "18 pt" },
  { value: "22pt", label: "22 pt" },
  { value: "26pt", label: "26 pt" },
  { value: "32pt", label: "32 pt" },
];

const FONT_FAMILIES = [
  { value: "", label: "默认字体" },
  { value: "SimSun", label: "宋体" },
  { value: "SimHei", label: "黑体" },
  { value: "FangSong", label: "仿宋" },
  { value: "KaiTi", label: "楷体" },
  { value: "Microsoft YaHei", label: "微软雅黑" },
];

const TEXT_COLORS = [
  "#1f2937", "#c00000", "#1f4f9a", "#0f766e", "#7c3aed", "#b45309",
  "#6b7280", "#ffffff",
];

const FontSize = Extension.create({
  name: "fontSize",
  addGlobalAttributes() {
    return [
      {
        types: ["textStyle"],
        attributes: {
          fontSize: {
            default: null,
            parseHTML: (element: HTMLElement) => element.style.fontSize || null,
            renderHTML: (attributes: Record<string, unknown>) =>
              attributes.fontSize ? { style: `font-size: ${String(attributes.fontSize)}` } : {},
          },
        },
      },
    ];
  },
});

const ParagraphLayout = Extension.create({
  name: "paragraphLayout",
  addGlobalAttributes() {
    return [
      {
        types: ["paragraph", "heading"],
        attributes: {
          lineHeight: {
            default: null,
            parseHTML: (element: HTMLElement) => element.style.lineHeight || null,
            renderHTML: (attributes: Record<string, unknown>) =>
              attributes.lineHeight ? { style: `line-height: ${String(attributes.lineHeight)}` } : {},
          },
          textIndent: {
            default: null,
            parseHTML: (element: HTMLElement) => element.style.textIndent || null,
            renderHTML: (attributes: Record<string, unknown>) =>
              attributes.textIndent ? { style: `text-indent: ${String(attributes.textIndent)}` } : {},
          },
        },
      },
    ];
  },
});

interface RichTextEditorProps {
  value: string;
  onChange: (html: string) => void;
  onReady?: (editor: Editor) => void;
}

function ToolButton({
  title,
  active = false,
  disabled = false,
  onClick,
  children,
}: {
  title: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Tooltip title={title}>
      <Button
        size="small"
        type={active ? "primary" : "text"}
        disabled={disabled}
        onClick={onClick}
        className="rt-tool-button"
      >
        {children}
      </Button>
    </Tooltip>
  );
}

function currentBlockType(editor: Editor): string {
  for (const level of [1, 2, 3, 4]) {
    if (editor.isActive("heading", { level })) return `h${level}`;
  }
  return "paragraph";
}

export function RichTextEditor({ value, onChange, onReady }: RichTextEditorProps) {
  const onChangeRef = useRef(onChange);
  const onReadyRef = useRef(onReady);
  const emittedRef = useRef("");
  const [, forceRender] = useReducer((tick: number) => tick + 1, 0);
  const [colorOpen, setColorOpen] = useState(false);
  const [tableOpen, setTableOpen] = useState(false);
  const [tableRows, setTableRows] = useState(3);
  const [tableColumns, setTableColumns] = useState(3);

  useEffect(() => {
    onChangeRef.current = onChange;
    onReadyRef.current = onReady;
  }, [onChange, onReady]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3, 4] } }),
      Underline,
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      ParagraphLayout,
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      Placeholder.configure({
        placeholder: "在此编写合同正文，可直接输入 {{甲方}}、{{合同金额}} 这类中文占位符。",
      }),
    ],
    content: toEditorHtml(value),
    editorProps: {
      attributes: { class: "rich-editor-content", spellcheck: "false" },
    },
    onUpdate: ({ editor: activeEditor }) => {
      const html = activeEditor.getHTML();
      emittedRef.current = html;
      onChangeRef.current(html);
    },
  });

  useEffect(() => {
    if (editor) onReadyRef.current?.(editor);
  }, [editor]);

  useEffect(() => {
    if (!editor) return;
    if (value === emittedRef.current) return;
    const html = sanitizeRichHtml(toEditorHtml(value));
    if (html !== editor.getHTML()) {
      editor.commands.setContent(html, false);
    }
    emittedRef.current = editor.getHTML();
  }, [editor, value]);

  useEffect(() => {
    if (!editor) return;
    const refresh = () => forceRender();
    editor.on("transaction", refresh);
    editor.on("selectionUpdate", refresh);
    return () => {
      editor.off("transaction", refresh);
      editor.off("selectionUpdate", refresh);
    };
  }, [editor]);

  if (!editor) {
    return <div className="rich-editor-shell rich-editor-loading">编辑器加载中…</div>;
  }

  const textStyle = editor.getAttributes("textStyle");
  const blockType = currentBlockType(editor);
  const layoutAttrs = editor.getAttributes(blockType) as {
    lineHeight?: string | null;
    textIndent?: string | null;
  };
  const inTable = editor.isActive("table");

  const applyParagraph = (patch: Record<string, string | null>) => {
    const type = editor.isActive("heading") ? "heading" : "paragraph";
    editor.chain().focus().updateAttributes(type, patch).run();
  };

  const setBlockType = (next: string) => {
    if (next === "paragraph") {
      editor.chain().focus().setParagraph().run();
      return;
    }
    const level = Number(next.slice(1)) as 1 | 2 | 3 | 4;
    editor.chain().focus().setHeading({ level }).run();
  };

  return (
    <div className="rich-editor-shell">
      <div className="rich-toolbar">
        <div className="rt-group">
          <ToolButton title="撤销" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()}>
            <UndoOutlined />
          </ToolButton>
          <ToolButton title="重做" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()}>
            <RedoOutlined />
          </ToolButton>
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <Select
            size="small"
            className="rt-select rt-block-select"
            value={blockType}
            onChange={setBlockType}
            options={[
              { value: "paragraph", label: "正文" },
              { value: "h1", label: "标题 1" },
              { value: "h2", label: "标题 2" },
              { value: "h3", label: "标题 3" },
              { value: "h4", label: "标题 4" },
            ]}
          />
          <Select
            size="small"
            className="rt-select rt-font-select"
            value={textStyle.fontFamily || ""}
            onChange={(next: string) => {
              if (next) editor.chain().focus().setFontFamily(next).run();
              else editor.chain().focus().unsetFontFamily().run();
            }}
            options={FONT_FAMILIES.map((item) => ({
              value: item.value,
              label: <span style={{ fontFamily: item.value || undefined }}>{item.label}</span>,
            }))}
          />
          <Select
            size="small"
            className="rt-select rt-size-select"
            value={(textStyle.fontSize as string) || ""}
            onChange={(next: string) => {
              editor.chain().focus().setMark("textStyle", { fontSize: next || null }).run();
            }}
            options={[{ value: "", label: "字号" }, ...FONT_SIZES]}
          />
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <ToolButton title="加粗（Ctrl+B）" active={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
            <BoldOutlined />
          </ToolButton>
          <ToolButton title="斜体（Ctrl+I）" active={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
            <ItalicOutlined />
          </ToolButton>
          <ToolButton title="下划线（Ctrl+U）" active={editor.isActive("underline")} onClick={() => editor.chain().focus().toggleUnderline().run()}>
            <UnderlineOutlined />
          </ToolButton>
          <ToolButton title="删除线" active={editor.isActive("strike")} onClick={() => editor.chain().focus().toggleStrike().run()}>
            <StrikethroughOutlined />
          </ToolButton>
          <Popover
            trigger="click"
            open={colorOpen}
            onOpenChange={setColorOpen}
            content={
              <div className="rt-color-panel">
                <div className="rt-color-grid">
                  {TEXT_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      className="rt-color-swatch"
                      style={{ background: color }}
                      title={color}
                      onClick={() => {
                        editor.chain().focus().setColor(color).run();
                        setColorOpen(false);
                      }}
                    />
                  ))}
                </div>
                <Button
                  size="small"
                  type="link"
                  onClick={() => {
                    editor.chain().focus().unsetColor().run();
                    setColorOpen(false);
                  }}
                >
                  恢复默认颜色
                </Button>
              </div>
            }
          >
            <Tooltip title="字体颜色">
              <Button size="small" type="text" className="rt-tool-button">
                <FontColorsOutlined />
              </Button>
            </Tooltip>
          </Popover>
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <ToolButton title="左对齐" active={editor.isActive({ textAlign: "left" })} onClick={() => editor.chain().focus().setTextAlign("left").run()}>
            <AlignLeftOutlined />
          </ToolButton>
          <ToolButton title="居中对齐" active={editor.isActive({ textAlign: "center" })} onClick={() => editor.chain().focus().setTextAlign("center").run()}>
            <AlignCenterOutlined />
          </ToolButton>
          <ToolButton title="右对齐" active={editor.isActive({ textAlign: "right" })} onClick={() => editor.chain().focus().setTextAlign("right").run()}>
            <AlignRightOutlined />
          </ToolButton>
          <ToolButton title="两端对齐" active={editor.isActive({ textAlign: "justify" })} onClick={() => editor.chain().focus().setTextAlign("justify").run()}>
            <span className="rt-justify-glyph">两端</span>
          </ToolButton>
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <ToolButton title="有序列表" active={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
            <OrderedListOutlined />
          </ToolButton>
          <ToolButton title="无序列表" active={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
            <UnorderedListOutlined />
          </ToolButton>
          <ToolButton title="引用段落" active={editor.isActive("blockquote")} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
            <span className="rt-quote-glyph">“”</span>
          </ToolButton>
          <ToolButton title="分隔线" onClick={() => editor.chain().focus().setHorizontalRule().run()}>
            <span className="rt-quote-glyph">—</span>
          </ToolButton>
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <Select
            size="small"
            className="rt-select rt-line-select"
            placeholder="行距"
            value={layoutAttrs.lineHeight || ""}
            onChange={(next: string) => applyParagraph({ lineHeight: next || null })}
            options={[
              { value: "", label: "默认行距" },
              { value: "1.5", label: "1.5 倍" },
              { value: "1.8", label: "1.8 倍" },
              { value: "2", label: "2 倍" },
              { value: "2.5", label: "2.5 倍" },
            ]}
          />
          <ToolButton
            title="首行缩进 2 字符"
            active={layoutAttrs.textIndent === "2em"}
            onClick={() => applyParagraph({ textIndent: layoutAttrs.textIndent === "2em" ? null : "2em" })}
          >
            <span className="rt-indent-glyph">首行缩进</span>
          </ToolButton>
        </div>
        <Divider type="vertical" />
        <div className="rt-group">
          <Popover
            trigger="click"
            open={tableOpen}
            onOpenChange={setTableOpen}
            content={
              <div className="rt-table-panel">
                <label>
                  行数
                  <InputNumber size="small" min={1} max={20} value={tableRows} onChange={(next) => setTableRows(Number(next) || 1)} />
                </label>
                <label>
                  列数
                  <InputNumber size="small" min={1} max={10} value={tableColumns} onChange={(next) => setTableColumns(Number(next) || 1)} />
                </label>
                <Button
                  type="primary"
                  size="small"
                  icon={<TableOutlined />}
                  onClick={() => {
                    editor.chain().focus().insertTable({ rows: tableRows, cols: tableColumns, withHeaderRow: true }).run();
                    setTableOpen(false);
                  }}
                >
                  插入表格
                </Button>
              </div>
            }
          >
            <Tooltip title="插入表格">
              <Button size="small" type={inTable ? "primary" : "text"} className="rt-tool-button">
                <TableOutlined />
              </Button>
            </Tooltip>
          </Popover>
          <ToolButton title="清除格式" onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}>
            <ClearOutlined />
          </ToolButton>
        </div>
      </div>

      {inTable && (
        <div className="rich-table-toolbar">
          <span><TableOutlined /> 表格工具</span>
          <Button size="small" onClick={() => editor.chain().focus().addRowBefore().run()}>上方插入行</Button>
          <Button size="small" onClick={() => editor.chain().focus().addRowAfter().run()}>下方插入行</Button>
          <Button size="small" onClick={() => editor.chain().focus().addColumnBefore().run()}>左侧插入列</Button>
          <Button size="small" onClick={() => editor.chain().focus().addColumnAfter().run()}>右侧插入列</Button>
          <Button size="small" icon={<MergeCellsOutlined />} onClick={() => editor.chain().focus().mergeCells().run()}>合并单元格</Button>
          <Button size="small" icon={<SplitCellsOutlined />} onClick={() => editor.chain().focus().splitCell().run()}>拆分单元格</Button>
          <Button size="small" onClick={() => editor.chain().focus().toggleHeaderRow().run()}>表头行</Button>
          <Button size="small" onClick={() => editor.chain().focus().deleteRow().run()}>删除行</Button>
          <Button size="small" onClick={() => editor.chain().focus().deleteColumn().run()}>删除列</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => editor.chain().focus().deleteTable().run()}>删除表格</Button>
        </div>
      )}

      <EditorContent editor={editor} />

      <div className="rich-editor-foot">
        <span><FontSizeOutlined /> 支持字号、行距、首行缩进、对齐、表格与颜色</span>
        <span>占位符支持中文，如 <code>{"{{甲方}}"}</code></span>
      </div>
    </div>
  );
}
