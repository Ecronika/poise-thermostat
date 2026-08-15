/* poise-card 0.191.0 — bundled, served by the Poise integration (ADR-0040) */
var Q=globalThis,ee=Q.ShadowRoot&&(Q.ShadyCSS===void 0||Q.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,fe=Symbol(),Re=new WeakMap,K=class{constructor(e,t,r){if(this._$cssResult$=!0,r!==fe)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(ee&&e===void 0){let r=t!==void 0&&t.length===1;r&&(e=Re.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),r&&Re.set(t,e))}return e}toString(){return this.cssText}},Le=n=>new K(typeof n=="string"?n:n+"",void 0,fe),U=(n,...e)=>{let t=n.length===1?n[0]:e.reduce((r,o,i)=>r+(s=>{if(s._$cssResult$===!0)return s.cssText;if(typeof s=="number")return s;throw Error("Value passed to 'css' function must be a 'css' function result: "+s+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(o)+n[i+1],n[0]);return new K(t,n,fe)},Oe=(n,e)=>{if(ee)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let r=document.createElement("style"),o=Q.litNonce;o!==void 0&&r.setAttribute("nonce",o),r.textContent=t.cssText,n.appendChild(r)}},_e=ee?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(let r of e.cssRules)t+=r.cssText;return Le(t)})(n):n;var{is:$t,defineProperty:Ct,getOwnPropertyDescriptor:kt,getOwnPropertyNames:St,getOwnPropertySymbols:At,getPrototypeOf:Et}=Object,te=globalThis,De=te.trustedTypes,Pt=De?De.emptyScript:"",Mt=te.reactiveElementPolyfillSupport,N=(n,e)=>n,ge={toAttribute(n,e){switch(e){case Boolean:n=n?Pt:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},Fe=(n,e)=>!$t(n,e),Ie={attribute:!0,type:String,converter:ge,reflect:!1,useDefault:!1,hasChanged:Fe};Symbol.metadata??=Symbol("metadata"),te.litPropertyMetadata??=new WeakMap;var $=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Ie){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let r=Symbol(),o=this.getPropertyDescriptor(e,r,t);o!==void 0&&Ct(this.prototype,e,o)}}static getPropertyDescriptor(e,t,r){let{get:o,set:i}=kt(this.prototype,e)??{get(){return this[t]},set(s){this[t]=s}};return{get:o,set(s){let l=o?.call(this);i?.call(this,s),this.requestUpdate(e,l,r)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Ie}static _$Ei(){if(this.hasOwnProperty(N("elementProperties")))return;let e=Et(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(N("properties"))){let t=this.properties,r=[...St(t),...At(t)];for(let o of r)this.createProperty(o,t[o])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[r,o]of t)this.elementProperties.set(r,o)}this._$Eh=new Map;for(let[t,r]of this.elementProperties){let o=this._$Eu(t,r);o!==void 0&&this._$Eh.set(o,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let r=new Set(e.flat(1/0).reverse());for(let o of r)t.unshift(_e(o))}else e!==void 0&&t.push(_e(e));return t}static _$Eu(e,t){let r=t.attribute;return r===!1?void 0:typeof r=="string"?r:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let r of t.keys())this.hasOwnProperty(r)&&(e.set(r,this[r]),delete this[r]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Oe(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,r){this._$AK(e,r)}_$ET(e,t){let r=this.constructor.elementProperties.get(e),o=this.constructor._$Eu(e,r);if(o!==void 0&&r.reflect===!0){let i=(r.converter?.toAttribute!==void 0?r.converter:ge).toAttribute(t,r.type);this._$Em=e,i==null?this.removeAttribute(o):this.setAttribute(o,i),this._$Em=null}}_$AK(e,t){let r=this.constructor,o=r._$Eh.get(e);if(o!==void 0&&this._$Em!==o){let i=r.getPropertyOptions(o),s=typeof i.converter=="function"?{fromAttribute:i.converter}:i.converter?.fromAttribute!==void 0?i.converter:ge;this._$Em=o;let l=s.fromAttribute(t,i.type);this[o]=l??this._$Ej?.get(o)??l,this._$Em=null}}requestUpdate(e,t,r,o=!1,i){if(e!==void 0){let s=this.constructor;if(o===!1&&(i=this[e]),r??=s.getPropertyOptions(e),!((r.hasChanged??Fe)(i,t)||r.useDefault&&r.reflect&&i===this._$Ej?.get(e)&&!this.hasAttribute(s._$Eu(e,r))))return;this.C(e,t,r)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:r,reflect:o,wrapped:i},s){r&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,s??t??this[e]),i!==!0||s!==void 0)||(this._$AL.has(e)||(this.hasUpdated||r||(t=void 0),this._$AL.set(e,t)),o===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[o,i]of this._$Ep)this[o]=i;this._$Ep=void 0}let r=this.constructor.elementProperties;if(r.size>0)for(let[o,i]of r){let{wrapped:s}=i,l=this[o];s!==!0||this._$AL.has(o)||l===void 0||this.C(o,void 0,i,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(r=>r.hostUpdate?.()),this.update(t)):this._$EM()}catch(r){throw e=!1,this._$EM(),r}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};$.elementStyles=[],$.shadowRootOptions={mode:"open"},$[N("elementProperties")]=new Map,$[N("finalized")]=new Map,Mt?.({ReactiveElement:$}),(te.reactiveElementVersions??=[]).push("2.1.2");var Ce=globalThis,Ke=n=>n,ne=Ce.trustedTypes,Ue=ne?ne.createPolicy("lit-html",{createHTML:n=>n}):void 0,We="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,qe="?"+C,Ht=`<${qe}>`,E=document,V=()=>E.createComment(""),B=n=>n===null||typeof n!="object"&&typeof n!="function",ke=Array.isArray,Tt=n=>ke(n)||typeof n?.[Symbol.iterator]=="function",be=`[ 	
\f\r]`,z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ne=/-->/g,ze=/>/g,S=RegExp(`>|${be}(?:([^\\s"'>=/]+)(${be}*=${be}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ve=/'/g,Be=/"/g,Ge=/^(?:script|style|textarea|title)$/i,Se=n=>(e,...t)=>({_$litType$:n,strings:e,values:t}),m=Se(1),Ye=Se(2),xn=Se(3),P=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),je=new WeakMap,A=E.createTreeWalker(E,129);function Xe(n,e){if(!ke(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ue!==void 0?Ue.createHTML(e):e}var Rt=(n,e)=>{let t=n.length-1,r=[],o,i=e===2?"<svg>":e===3?"<math>":"",s=z;for(let l=0;l<t;l++){let a=n[l],u,f,h=-1,g=0;for(;g<a.length&&(s.lastIndex=g,f=s.exec(a),f!==null);)g=s.lastIndex,s===z?f[1]==="!--"?s=Ne:f[1]!==void 0?s=ze:f[2]!==void 0?(Ge.test(f[2])&&(o=RegExp("</"+f[2],"g")),s=S):f[3]!==void 0&&(s=S):s===S?f[0]===">"?(s=o??z,h=-1):f[1]===void 0?h=-2:(h=s.lastIndex-f[2].length,u=f[1],s=f[3]===void 0?S:f[3]==='"'?Be:Ve):s===Be||s===Ve?s=S:s===Ne||s===ze?s=z:(s=S,o=void 0);let b=s===S&&n[l+1].startsWith("/>")?" ":"";i+=s===z?a+Ht:h>=0?(r.push(u),a.slice(0,h)+We+a.slice(h)+C+b):a+C+(h===-2?l:b)}return[Xe(n,i+(n[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),r]},j=class n{constructor({strings:e,_$litType$:t},r){let o;this.parts=[];let i=0,s=0,l=e.length-1,a=this.parts,[u,f]=Rt(e,t);if(this.el=n.createElement(u,r),A.currentNode=this.el.content,t===2||t===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(o=A.nextNode())!==null&&a.length<l;){if(o.nodeType===1){if(o.hasAttributes())for(let h of o.getAttributeNames())if(h.endsWith(We)){let g=f[s++],b=o.getAttribute(h).split(C),w=/([.?@])?(.*)/.exec(g);a.push({type:1,index:i,name:w[2],strings:b,ctor:w[1]==="."?ye:w[1]==="?"?xe:w[1]==="@"?we:R}),o.removeAttribute(h)}else h.startsWith(C)&&(a.push({type:6,index:i}),o.removeAttribute(h));if(Ge.test(o.tagName)){let h=o.textContent.split(C),g=h.length-1;if(g>0){o.textContent=ne?ne.emptyScript:"";for(let b=0;b<g;b++)o.append(h[b],V()),A.nextNode(),a.push({type:2,index:++i});o.append(h[g],V())}}}else if(o.nodeType===8)if(o.data===qe)a.push({type:2,index:i});else{let h=-1;for(;(h=o.data.indexOf(C,h+1))!==-1;)a.push({type:7,index:i}),h+=C.length-1}i++}}static createElement(e,t){let r=E.createElement("template");return r.innerHTML=e,r}};function T(n,e,t=n,r){if(e===P)return e;let o=r!==void 0?t._$Co?.[r]:t._$Cl,i=B(e)?void 0:e._$litDirective$;return o?.constructor!==i&&(o?._$AO?.(!1),i===void 0?o=void 0:(o=new i(n),o._$AT(n,t,r)),r!==void 0?(t._$Co??=[])[r]=o:t._$Cl=o),o!==void 0&&(e=T(n,o._$AS(n,e.values),o,r)),e}var ve=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:r}=this._$AD,o=(e?.creationScope??E).importNode(t,!0);A.currentNode=o;let i=A.nextNode(),s=0,l=0,a=r[0];for(;a!==void 0;){if(s===a.index){let u;a.type===2?u=new W(i,i.nextSibling,this,e):a.type===1?u=new a.ctor(i,a.name,a.strings,this,e):a.type===6&&(u=new $e(i,this,e)),this._$AV.push(u),a=r[++l]}s!==a?.index&&(i=A.nextNode(),s++)}return A.currentNode=E,o}p(e){let t=0;for(let r of this._$AV)r!==void 0&&(r.strings!==void 0?(r._$AI(e,r,t),t+=r.strings.length-2):r._$AI(e[t])),t++}},W=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,r,o){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=r,this.options=o,this._$Cv=o?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=T(this,e,t),B(e)?e===d||e==null||e===""?(this._$AH!==d&&this._$AR(),this._$AH=d):e!==this._$AH&&e!==P&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Tt(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==d&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(E.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:r}=e,o=typeof r=="number"?this._$AC(e):(r.el===void 0&&(r.el=j.createElement(Xe(r.h,r.h[0]),this.options)),r);if(this._$AH?._$AD===o)this._$AH.p(t);else{let i=new ve(o,this),s=i.u(this.options);i.p(t),this.T(s),this._$AH=i}}_$AC(e){let t=je.get(e.strings);return t===void 0&&je.set(e.strings,t=new j(e)),t}k(e){ke(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,r,o=0;for(let i of e)o===t.length?t.push(r=new n(this.O(V()),this.O(V()),this,this.options)):r=t[o],r._$AI(i),o++;o<t.length&&(this._$AR(r&&r._$AB.nextSibling,o),t.length=o)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let r=Ke(e).nextSibling;Ke(e).remove(),e=r}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},R=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,r,o,i){this.type=1,this._$AH=d,this._$AN=void 0,this.element=e,this.name=t,this._$AM=o,this.options=i,r.length>2||r[0]!==""||r[1]!==""?(this._$AH=Array(r.length-1).fill(new String),this.strings=r):this._$AH=d}_$AI(e,t=this,r,o){let i=this.strings,s=!1;if(i===void 0)e=T(this,e,t,0),s=!B(e)||e!==this._$AH&&e!==P,s&&(this._$AH=e);else{let l=e,a,u;for(e=i[0],a=0;a<i.length-1;a++)u=T(this,l[r+a],t,a),u===P&&(u=this._$AH[a]),s||=!B(u)||u!==this._$AH[a],u===d?e=d:e!==d&&(e+=(u??"")+i[a+1]),this._$AH[a]=u}s&&!o&&this.j(e)}j(e){e===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},ye=class extends R{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===d?void 0:e}},xe=class extends R{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==d)}},we=class extends R{constructor(e,t,r,o,i){super(e,t,r,o,i),this.type=5}_$AI(e,t=this){if((e=T(this,e,t,0)??d)===P)return;let r=this._$AH,o=e===d&&r!==d||e.capture!==r.capture||e.once!==r.once||e.passive!==r.passive,i=e!==d&&(r===d||o);o&&this.element.removeEventListener(this.name,this,r),i&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},$e=class{constructor(e,t,r){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=r}get _$AU(){return this._$AM._$AU}_$AI(e){T(this,e)}};var Lt=Ce.litHtmlPolyfillSupport;Lt?.(j,W),(Ce.litHtmlVersions??=[]).push("3.3.3");var Ze=(n,e,t)=>{let r=t?.renderBefore??e,o=r._$litPart$;if(o===void 0){let i=t?.renderBefore??null;r._$litPart$=o=new W(e.insertBefore(V(),i),i,void 0,t??{})}return o._$AI(n),o};var Ae=globalThis,x=class extends ${constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=Ze(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return P}};x._$litElement$=!0,x.finalized=!0,Ae.litElementHydrateSupport?.({LitElement:x});var Ot=Ae.litElementPolyfillSupport;Ot?.({LitElement:x});(Ae.litElementVersions??=[]).push("4.2.2");function Dt(n,e,t){return Math.min(Math.max(n,e),t)}function re(n,e,t){return t<=e?.5:Dt((n-e)/(t-e),0,1)}function It(n,e,t){if(n==null)return"unknown";if(n<e)return"below";if(n>t)return"above";let r=t-e;if(r<=0)return"in_band";let o=(n-e)/r;return o<.25?"cool_edge":o>.75?"warm_edge":"in_band"}function Je(n){let{operative:e,setpoint:t,low:r,high:o}=n;if(r==null||o==null||o<=r)return null;let i=r-1.5,s=o+1.5;return{low:r,high:o,span:o-r,operative:e,setpoint:t,category:n.category??"",verdict:It(e,r,o),axisLow:i,axisHigh:s,lowFrac:re(r,i,s),highFrac:re(o,i,s),operativeFrac:e==null?null:re(e,i,s),setpointFrac:t==null?null:re(t,i,s)}}var Qe={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function L(n){return Qe[n]??Qe.unknown}var Ft=[1e3,2e3],Kt=[30,40,60,65],Ut=[5,7],Nt=[26,30],zt=420,Vt=[800,1350];function _(n){return typeof n=="number"&&Number.isFinite(n)}function q(n,e){return n&&n.length>=2&&_(n[0])&&_(n[1])&&n[0]<n[1]?[n[0],n[1]]:[e[0],e[1]]}function Bt(n,e){if(n&&n.length>=4&&n.slice(0,4).every(_)){let[t,r,o,i]=n;if(t<=r&&r<=o&&o<=i)return[t,r,o,i]}return[e[0],e[1],e[2],e[3]]}function jt(n){if(n?.scheme==="en16798"){let e=_(n.outdoor)?n.outdoor:zt,t=q(n.enRise,Vt);return[e+t[0],e+t[1]]}return q(n?.thresholds,Ft)}function Wt(n,e){if(!_(n))return"unknown";let[t,r]=jt(e);return n>=r?"alert":n>=t?"warn":"ok"}function qt(n,e,t,r){if(!_(n))return"unknown";let[o,i,s,l]=Bt(e,Kt);if(n>=l)return"alert";if(_(t)){let[a,u]=q(r,Ut);return t<a?"alert":t<u||n>s?"warn":"ok"}return n<o?"alert":n<i||n>s?"warn":"ok"}function Gt(n){switch(n){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Yt(n,e){if(!_(n))return"unknown";let[t,r]=q(e,Nt);return n>r?"alert":n>t?"warn":"ok"}var Xt=[10,15];function Zt(n){return 100-95*Math.exp(-(.03353*n**4+.2179*n**2))}function Jt(n,e,t){let[r,o]=q(t,Xt),i=_(e)?e:_(n)?Zt(n):null;return i==null?"unknown":i>=o?"alert":i>=r?"warn":"ok"}var Qt=[.5,1],en=[3,6],tn=[85,60];function tt(n){return n<=1?n*100:n}var et={unknown:-1,ok:0,warn:1,alert:2};function nn(n){let e=[];if(_(n.deviationK)){let[t,r]=Qt;e.push(n.deviationK>=r?"alert":n.deviationK>=t?"warn":"ok")}if(_(n.cyclesPerH)){let[t,r]=en;e.push(n.cyclesPerH>=r?"alert":n.cyclesPerH>=t?"warn":"ok")}if(_(n.timeInBand)){let t=tt(n.timeInBand),[r,o]=tn;e.push(t<o?"alert":t<r?"warn":"ok")}return e.length?e.reduce((t,r)=>et[r]>et[t]?r:t,"ok"):"unknown"}function nt(n){if(!n.active)return null;let e=n.fanFirstPhase==="await_fan_only"||n.fanFirstPhase==="await_stage"||n.fanFirstPhase==="dwell",t=_(n.ceCreditK)&&n.ceCreditK>0?n.ceCreditK:null,r=_(n.pmvOffsetK)&&n.pmvOffsetK!==0?n.pmvOffsetK:null,o=n.tier2FanCe==="eligible"?"fan_ce":n.tier2Pmv==="eligible"?"pmv_offset":null,i=!e&&t==null&&r==null&&o!=null,s=null,l=null,a=!1;if(i){let u=o==="fan_ce"?n.fanCeDwellMin:n.pmvDwellMin;s=_(u)&&u>=0?u:null,l=_(n.dwellTargetMin)&&n.dwellTargetMin>0?n.dwellTargetMin:null,a=n.dwelling!=null&&n.dwelling!==o}return{fan:e,ceK:t,offsetK:r,maturing:i,dwellMin:s,dwellTargetMin:l,dwellPaused:a}}function rt(n,e){let t=[],r=e?.temperature_scale==="asr_office"?Yt(n.temperature,e.asr_thresholds):Gt(n.comfortVerdict??null);if(t.push({key:"temperature",value:n.temperature,unit:"\xB0C",level:r,color:L(r)}),_(n.humidity)){let i=n.absHumidityGm3??null,s=qt(n.humidity,e?.humidity_thresholds,i,e?.abs_humidity_floors);t.push({key:"humidity",value:n.humidity,unit:"%",level:s,color:L(s),..._(i)?{detail:`${i.toFixed(1)} g/m\xB3`}:{}})}if(_(n.co2)){let i=Wt(n.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:n.co2,unit:"ppm",level:i,color:L(i)})}if(n.pmvValid===!1)t.push({key:"pmv",value:null,unit:"%",level:"unknown",color:L("unknown"),detailKey:"pmv_not_validated"});else if(_(n.pmv)||_(n.ppd)){let i=Jt(n.pmv??null,n.ppd??null);t.push({key:"pmv",value:_(n.ppd)?100-n.ppd:null,unit:"%",level:i,color:L(i)})}let o=n.ca;if(o&&(_(o.deviationK)||_(o.timeInBand)||_(o.cyclesPerH))){let i=nn(o);t.push({key:"ca",value:_(o.timeInBand)?tt(o.timeInBand):null,unit:"%",level:i,color:L(i)})}return t}var Ee=["hvac","window","temperature","humidity","co2","ca"],rn=[12,24,48];function ot(n,e,t){return typeof n=="string"&&e.includes(n)?n:t}function O(n,e){return typeof n=="boolean"?n:e}function on(n){return n===!1?new Set:n==null||n===!0?new Set(Ee):Array.isArray(n)?new Set(n.filter(e=>Ee.includes(e))):new Set(Ee)}function sn(n){if(n===!1)return{show:!1,hours:24};if(n===!0||n==null)return{show:!0,hours:24};let e=typeof n.hours=="number"?n.hours:Number(n.hours),t=rn.includes(e)?e:24;return{show:O(n.show,!0),hours:t}}function it(n){let e=n.sections??{},t=n.density?ot(n.density,["comfortable","compact"],"comfortable"):n.compact?"compact":"comfortable";return{entity:n.entity,density:t,controls:ot(n.controls,["dial","buttons","none"],"dial"),history:sn(n.history),chips:on(e.chips),shadowPill:O(e.shadow_pill,O(n.show_shadow,!0)),learning:O(e.learning,!0),pmv:O(e.pmv,!0),presets:O(e.presets,!0),temperature_scale:n.temperature_scale,humidity_thresholds:n.humidity_thresholds,abs_humidity_floors:n.abs_humidity_floors,co2_scheme:n.co2_scheme,co2_thresholds:n.co2_thresholds}}var st={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",pmv_ok:"OK",pmv_warn:"Fair",pmv_alert:"Low",ca_ok:"OK",ca_warn:"Reduced",ca_alert:"Poor",pmv_not_validated:"not validated (outside ISO 7730)",ac_active:"Comfort active",ac_fan:"fan first",ac_ce:"cool edge",ac_maturing:"maturing",ac_maturing_paused:"maturing (paused)",ac_none:"no measure active",override_clamped:"Setpoint clamped",manual:"Manual",resume_schedule:"Resume schedule",valid_until:"valid until",instead_of:"instead of",norm_limit:"norm limit",permanent:"permanent",operative:"operative",air:"air",cools:"cooling",heats:"heating",dries:"drying",origin_device:"device",origin_app:"app",compressor_guard:"Compressor guard",mould:"Mould limit",binding_mold:"Mould guard holds the minimum",binding_frost:"Frost guard holds the minimum",mode_off:"Off",mode_heat:"Heating",mode_cool:"Cooling",mode_dry:"Drying",mode_fan_only:"Fan",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical",vent_open:"Air out",vent_mold_risk:"mould risk",vent_moisture_out:"moisture",vent_co2:"CO\u2082",vent_heat_out:"cooler outside"},an={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",pmv_ok:"OK",pmv_warn:"M\xE4\xDFig",pmv_alert:"Gering",ca_ok:"OK",ca_warn:"Eingeschr\xE4nkt",ca_alert:"Schlecht",pmv_not_validated:"nicht validiert (au\xDFerhalb ISO 7730)",ac_active:"Behaglichkeit aktiv",ac_fan:"L\xFCfter zuerst",ac_ce:"K\xFChlkante",ac_maturing:"reift",ac_maturing_paused:"reift (pausiert)",ac_none:"keine Ma\xDFnahme aktiv",override_clamped:"Sollwert geklemmt",manual:"Manuell",resume_schedule:"Zeitplan fortsetzen",valid_until:"gilt bis",instead_of:"statt",norm_limit:"Normgrenze",permanent:"dauerhaft",operative:"operativ",air:"Luft",cools:"k\xFChlt",heats:"heizt",dries:"entfeuchtet",origin_device:"Ger\xE4t",origin_app:"App",compressor_guard:"Verdichterschutz",mould:"Schimmelgrenze",binding_mold:"Schimmelschutz h\xE4lt die Untergrenze",binding_frost:"Frostschutz h\xE4lt die Untergrenze",mode_off:"Aus",mode_heat:"Heizen",mode_cool:"K\xFChlen",mode_dry:"Entfeuchten",mode_fan_only:"L\xFCfter",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch",vent_open:"L\xFCften",vent_mold_risk:"Schimmelrisiko",vent_moisture_out:"Feuchte",vent_co2:"CO\u2082",vent_heat_out:"drau\xDFen k\xFChler"};function c(n,e){return((n??"en").toLowerCase().startsWith("de")?an:st)[e]??st[e]??e}var ln=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],cn=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:ln}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],un={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},oe=class extends x{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${cn}
      .computeLabel=${e=>un[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};oe.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",oe);var ie="0.191.0",at=!1;function dn(){let n=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(n,n):n()}async function se(n,e){if(!(at||!e?.connection)){at=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==ie){let r=e.locale?.language;n.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${c(r,"update_msg")} (${ie} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:c(r,"reload"),action:dn}},bubbles:!0,composed:!0}))}}catch{}}}function G(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var Y=class extends x{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(r=>r.startsWith("binary_sensor.")&&e.states[r].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&se(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,r=t?this.hass.states[t]:void 0;if(!r)return m`<ha-card
        ><div class="empty">${c(e,"no_system")}</div></ha-card
      >`;let o=r.attributes,i=r.state==="on",s=G(o.flow_target),l=G(o.shed_count)??0,a=o.source_grants??{},u=Object.keys(a);return m`<ha-card .header=${c(e,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${c(e,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${i?"on":""}">
          <ha-icon icon=${i?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${i?c(e,"demand_on"):c(e,"demand_off")}</span>
          ${o.frost_override?m`<em class="frost">${c(e,"frost")}</em>`:d}
        </div>
        <div class="stats">
          <div>
            <strong>${G(o.active_zones)??0}</strong
            ><span>${c(e,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${G(o.controlling_zones)??0}/${G(o.zone_count)??0}</strong
            ><span>${c(e,"zones")}</span>
          </div>
          ${s!=null?m`<div>
                <strong>${s.toFixed(0)}°</strong><span>${c(e,"flow")}</span>
              </div>`:d}
          ${l>0?m`<div>
                <strong>${l}</strong><span>${c(e,"shed")}</span>
              </div>`:d}
        </div>
        ${u.length?m`<div class="grants">
              ${u.map(f=>m`<span class="chip">${f}: ${a[f]}</span>`)}
            </div>`:d}
      </div>
    </ha-card>`}};Y.properties={hass:{},_config:{state:!0}},Y.styles=U`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .wrap:focus { outline: none; }
    .wrap:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: -2px; border-radius: 10px;
    }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var ae=class extends x{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${e=>e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};ae.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",ae);customElements.get("poise-system-card")||customElements.define("poise-system-card",Y);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function ct(n,e){return`${n}|${e}`}function ut(n,e,t,r=3e5,o=3e4){return n===null||n.key!==e?!0:n.failedAt!=null?t-n.failedAt>=o:t-n.at>=r}function Pe(n,e){return n?.key===e}function lt(n,e,t){return Math.min(Math.max(n,e),t)}function dt(n,e,t,r=300,o=90,i=1){let s=[];for(let v of n)v.op!=null&&s.push(v.op),v.sp!=null&&s.push(v.sp);if(e!=null&&s.push(e),t!=null&&s.push(t),s.length===0||n.length===0)return null;let l=Math.min(...s)-i,a=Math.max(...s)+i,u=n[0].t,h=n[n.length-1].t-u||1,g=a-l||1,b=v=>(v-u)/h*r,w=v=>o-(v-l)/g*o,Z=v=>n.filter(M=>v(M)!=null).map(M=>`${b(M.t).toFixed(1)},${w(v(M)).toFixed(1)}`).join(" ");return{width:r,height:o,opPath:Z(v=>v.op),spPath:Z(v=>v.sp),bandTop:t==null?0:lt(w(t),0,o),bandBottom:e==null?o:lt(w(e),0,o),vMin:l,vMax:a}}var y={min:16,max:28,start:135,sweep:270};function pt(n,e,t){return Math.min(Math.max(n,e),t)}function D(n,e=y){let t=pt((n-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function pn(n,e=y){let t=n;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let r=t-(e.start+e.sweep);return e.start+360-t<r?e.start:e.start+e.sweep}function hn(n,e=y){let r=(pn(n,e)-e.start)/e.sweep;return e.min+r*(e.max-e.min)}function k(n,e,t,r){let o=r*Math.PI/180;return{x:n+t*Math.cos(o),y:e+t*Math.sin(o)}}function Me(n,e,t,r,o){if(o<=r)return"";let i=k(n,e,t,r),s=k(n,e,t,o),l=o-r>180?1:0;return`M ${i.x.toFixed(2)} ${i.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${s.x.toFixed(2)} ${s.y.toFixed(2)}`}function ht(n,e,t=y){let r=Math.atan2(e,n)*180/Math.PI;return r<0&&(r+=360),hn(r,t)}function mt(n,e,t,r=y){let o;switch(n){case"ArrowUp":case"ArrowRight":o=e+t;break;case"ArrowDown":case"ArrowLeft":o=e-t;break;case"PageUp":o=e+t*5;break;case"PageDown":o=e-t*5;break;case"Home":o=r.min;break;case"End":o=r.max;break;default:return null}return Math.round(pt(o,r.min,r.max)/t)*t}function He(n,e=Date.now()){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:Math.max(0,Math.round((t-e)/6e4))}function ft(n,e){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:new Date(t).toLocaleTimeString(e,{hour:"2-digit",minute:"2-digit"})}function I(n){let e=n.temperature,t=typeof e=="string"?parseFloat(e):e;return typeof t=="number"&&!Number.isNaN(t)?t:null}function le(n){let e=n.target_temp_step,t=typeof e=="string"?parseFloat(e):e;return typeof t=="number"&&!Number.isNaN(t)&&t>0?t:.5}function mn(n,e){let t=typeof e=="string"?e:"";return t.startsWith("device_adopt")?c(n,"origin_device"):t.startsWith("ui")?c(n,"origin_app"):null}function fn(n,e){let t=typeof e=="string"?e.toLowerCase():"";return t==="cooling"?c(n,"cools"):t==="heating"?c(n,"heats"):t==="drying"?c(n,"dries"):null}function _n(n,e){if(typeof e!="string"||e==="")return null;let t=`mode_${e}`,r=c(n,t);return r===t?e:r}function _t(n,e,t,r,o=Date.now(),i=null,s=null,l=null,a=!0){let u=c(n,"manual"),f=fn(n,i),h=mn(n,s),g=_n(n,l),b=g!=null?` \xB7 ${g}`:"";return t==="permanent"?{label:`${u} (${c(n,"permanent")})${b}`,minutes:null,permanent:!0,direction:f,origin:h}:{label:a&&e!=null?`${u} ${e.toFixed(1)}\xB0${b}`:`${u}${b}`,minutes:He(r,o),permanent:!1,direction:f,origin:h}}function gt(n,e,t=.3){return n==null||e==null?null:Math.abs(n-e)>=t?e:null}function bt(n,e,t){return e==null||t==null?c(n,"override_clamped"):`${e.toFixed(1)}\xB0 ${c(n,"instead_of")} ${t.toFixed(1)}\xB0 (${c(n,"norm_limit")})`}function vt(n,e,t){let r=e==null?"none":String(e).toLowerCase();return r==="none"||t?null:{key:r,label:c(n,r)||r}}function yt(n,e){n.callService("poise","resume_schedule",{entity_id:e})}function xt(n){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[n]??"mdi:tune"}function p(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var X=class extends x{constructor(){super(...arguments);this._history=[];this._histSync=null;this._dragging=!1;this._pending=null;this._dialCfg=y}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(o=>o.startsWith("climate.")&&t.states[o].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=it(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let r=t.get("hass");return!r||!this._config?.entity?!0:r.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let r=this._config.entity;if(!r||!this.hass)return;let o=this.hass.states[r];if(!o)return;let i=le(o.attributes),s=this._pending??I(o.attributes)??21;this.hass.callService("climate","set_temperature",{entity_id:r,temperature:Math.round((s+t*i)*10)/10})}connectedCallback(){super.connectedCallback(),this._histTimer=setInterval(()=>this._syncHistory(),6e4)}disconnectedCallback(){clearInterval(this._histTimer),this._histTimer=void 0,super.disconnectedCallback()}updated(){this.hass&&se(this,this.hass),this._syncHistory()}_syncHistory(){let t=this._config?.entity;if(!t||!this.hass||!this._r?.history.show)return;let r=ct(t,this._r.history.hours);ut(this._histSync,r,Date.now())&&(this._histSync={key:r,at:Date.now(),failedAt:null},this._loadHistory(t,r))}async _loadHistory(t,r){if(!this.hass.connection)return;let o=this._r?.history.hours??24,i=new Date,s=new Date(i.getTime()-o*3600*1e3);try{let a=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:s.toISOString(),end_time:i.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],u={},f=[];for(let h of a){h.a&&(u={...u,...h.a});let g=(p(h.lu)??p(h.lc)??0)*1e3;f.push({t:g,op:p(u.operative_temperature)??p(u.current_temperature),sp:p(u.temperature)})}if(!Pe(this._histSync,r))return;this._history=f,this.requestUpdate()}catch{Pe(this._histSync,r)&&(this._histSync={key:r,at:0,failedAt:Date.now()})}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,r){let o=dt(this._history,t,r,300,80);return o?m`<svg
      class="chart"
      viewBox="0 0 ${o.width} ${o.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${o.bandTop}
        width=${o.width}
        height=${Math.max(0,o.bandBottom-o.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${o.spPath} class="csp"></polyline>
      <polyline points=${o.opPath} class="cop"></polyline>
    </svg>`:d}render(){let t=this.hass?.locale?.language,r=this._config?.entity,o=r?this.hass.states[r]:void 0;if(!o)return m`<ha-card
        ><div class="empty">${c(t,"no_entity")}</div></ha-card
      >`;let i=o.attributes,s=p(i.operative_temperature)??p(i.current_temperature),l=p(i.heat_sp)??p(i.temperature),a=Je({operative:s,setpoint:l,low:p(i.comfort_low),high:p(i.comfort_high),category:i.category??null}),u=this._r;return m`<ha-card .header=${i.friendly_name??"Poise"}>
      <div class="wrap ${u.density==="compact"?"compact":""}">
        ${this._dial(i,t)}
        <div class="verdict">
          ${a?c(t,a.verdict):c(t,"unknown")}
          ${a?.category?m`<span class="cat">Kat. ${a.category}</span>`:d}
        </div>
        ${this._holdPill(i,t)}
        ${u.controls==="buttons"?this._control(this._pending??l,t):d}
        ${this._presets(i,t)}
        ${u.history.show?this._chart(p(i.comfort_low),p(i.comfort_high)):d}
        ${this._monitor(i,a,t)} ${this._measurePill(i,t)}
        ${this._chips(i,t)} ${this._learn(i,t)}
      </div>
    </ha-card>`}_dial(t,r){let o=p(t.operative_temperature)??p(t.current_temperature),i=gt(o,p(t.current_temperature)),s=I(t),l={min:p(t.min_temp)??y.min,max:p(t.max_temp)??y.max,start:y.start,sweep:y.sweep};this._dialCfg=l.max>l.min?l:y;let a=this._pending??s??o??this._dialCfg.min,u=p(t.comfort_low),f=p(t.comfort_high),h=100,g=100,b=80,w=Me(h,g,b,y.start,y.start+y.sweep),Z=u!=null&&f!=null?Me(h,g,b,D(Math.min(u,f),this._dialCfg),D(Math.max(u,f),this._dialCfg)):"",v=String(t.hvac_action??""),M=v==="heating"?"heat":v==="cooling"?"cool":"",Te=k(h,g,b,D(a,this._dialCfg)),ce=o!=null?k(h,g,b,D(o,this._dialCfg)):null,H=p(t.mould_floor),F=H!=null&&H>this._dialCfg.min&&H<this._dialCfg.max,ue=F?D(H,this._dialCfg):0,de=F?k(h,g,b-9,ue):null,pe=F?k(h,g,b+9,ue):null,he=F?k(h,g,b+17,ue):null,me=this._r.controls==="dial",J=this._dragging?ft(t.override_expires_at,r):null,wt=`${a.toFixed(1)} \xB0C${J?` \xB7 ${c(r,"valid_until")} ${J}`:""}`;return m`<div class="dialwrap">
      <svg
        class="dial ${me?"":"ro"}"
        viewBox="0 0 200 200"
        role=${me?"slider":"img"}
        tabindex=${me?0:-1}
        aria-label=${c(r,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${a}
        aria-valuetext=${wt}
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${w}></path>
        <path class="bandarc" d=${Z}></path>
        ${F&&de&&pe&&he?Ye`<line class="mould" x1=${de.x.toFixed(1)} y1=${de.y.toFixed(1)} x2=${pe.x.toFixed(1)} y2=${pe.y.toFixed(1)}><title>${c(r,"mould")} ${H.toFixed(1)}°</title></line><text class="mlbl" x=${he.x.toFixed(1)} y=${he.y.toFixed(1)}>${H.toFixed(0)}°</text>`:d}
        <circle
          class="opdot"
          cx=${(ce?.x??0).toFixed(1)}
          cy=${(ce?.y??0).toFixed(1)}
          r=${ce?5:0}
        ></circle>
        <circle class="handle ${M}" cx=${Te.x.toFixed(1)} cy=${Te.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${c(r,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op" title=${c(r,"operative")}>${o!=null?o.toFixed(1):"\u2014"}<span>°C</span></div>
          ${i!=null?m`<div class="opair">${c(r,"operative")} · ${c(r,"air")} ${i.toFixed(1)}°</div>`:d}
          <div class="soll">${c(r,"setpoint")} <b>${a.toFixed(1)}°</b></div>
          ${J?m`<div class="valid">${c(r,"valid_until")} ${J}</div>`:d}
        </div>
      </div>
    </div>`}_fromPointer(t,r){let o=r.getBoundingClientRect();if(!o.width||!this._config.entity)return;let i=(t.clientX-o.left)/o.width*200-100,s=(t.clientY-o.top)/o.height*200-100,l=le(this.hass.states[this._config.entity]?.attributes??{});this._pending=Math.round(ht(i,s,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let r=t.currentTarget;r.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,r)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let r=this._config.entity;if(!r||this._r.controls!=="dial")return;let o=this.hass.states[r];if(!o)return;let i=le(o.attributes),s=this._pending??I(o.attributes)??this._dialCfg.min,l=mt(t.key,s,i,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:r,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,r){return m`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${c(r,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let r=this._config.entity;!r||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:r,preset_mode:t})}_resumeSchedule(){let t=this._config.entity;!t||!this.hass||yt(this.hass,t)}_presets(t,r){if(!this._r.presets)return d;let o=t.preset_modes;if(!Array.isArray(o)||!o.length)return d;let i=t.preset_mode==null?null:String(t.preset_mode),s=He(t.boost_expires_at);return m`<div class="presets" role="group" aria-label=${c(r,"presets")}>
      ${o.map(l=>{let a=String(l),u=a.toLowerCase();return m`<button
          class="preset ${i===a?"on":""}"
          aria-pressed=${i===a?"true":"false"}
          @click=${()=>this._setPreset(a)}
        >
          <ha-icon icon=${xt(u)}></ha-icon>
          <span>${c(r,u)||a}</span>
          ${u==="boost"&&s!=null?m`<em>${s} ${c(r,"min_left")}</em>`:d}
        </button>`})}
    </div>`}_holdPill(t,r){if(!t.override_active)return d;let o=I(t),i=_t(r,o,t.override_policy,t.override_expires_at,Date.now(),t.hvac_action,t.override_reason,t.mode_override,t.override_requested!=null);return m`<div class="hold">
      <div class="chip hold-chip">
        <ha-icon icon="mdi:hand-back-right"></ha-icon><span>${i.label}</span>
        ${i.direction!=null?m`<em>· ${i.direction}</em>`:d}
        ${i.origin!=null?m`<em>· ${i.origin}</em>`:d}
        ${i.minutes!=null?m`<em>· ${i.minutes} ${c(r,"min_left")}</em>`:d}
      </div>
      <button
        class="resume"
        aria-label=${c(r,"resume_schedule")}
        title=${c(r,"resume_schedule")}
        @click=${this._resumeSchedule}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`}_chips(t,r){let o=this._r,i=[];if(o.chips.has("hvac")){t.preheating&&i.push(this._chip("mdi:fire-circle",c(r,"preheating"),t.minutes_to_comfort,r)),t.coasting&&i.push(this._chip("mdi:coffee",c(r,"coasting"),t.minutes_to_setback,r));let s=vt(r,t.preset,o.presets);s&&i.push(this._chip(xt(s.key),s.label)),t.heating_failure&&i.push(this._chip("mdi:alert",c(r,"failure"))),t.override_clamped&&i.push(this._chip("mdi:arrow-collapse-vertical",bt(r,I(t),p(t.override_requested)))),t.mode_nudge_blocked&&i.push(this._chip("mdi:timer-sand",`${c(r,"compressor_guard")}: ${t.mode_nudge_blocked}`));let l=t.binding_lower_cause;if(l&&l!=="en16798"){let a=`binding_${l}`,u=c(r,a);i.push(this._chip(l==="frost"?"mdi:snowflake-alert":"mdi:water-alert",u===a?String(l):u))}}if(o.chips.has("window")&&(t.window_open&&i.push(this._chip("mdi:window-open",c(r,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&i.push(this._chip("mdi:window-closed-variant",c(r,"bypass")))),o.chips.has("humidity")&&t.vent_action==="open"){let s=String(t.vent_reason??""),a=["mold_risk","moisture_out","co2","heat_out"].includes(s)?`${c(r,"vent_open")} (${c(r,"vent_"+s)})`:c(r,"vent_open");i.push(this._chip("mdi:weather-windy",a,void 0,r,t.vent_level==="alert"))}return i.length?m`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${c(r,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${i}
        </div>`:d}_chip(t,r,o,i,s=!1){let l=p(o);return m`<div class="chip ${s?"chip-alert":""}">
      <ha-icon icon=${t}></ha-icon><span>${r}</span>
      ${l!=null?m`<em>${Math.round(l)} ${c(i,"min_left")}</em>`:d}
    </div>`}_monitor(t,r,o){let i=rt({temperature:p(t.operative_temperature)??p(t.current_temperature),comfortVerdict:r?.verdict??null,humidity:p(t.humidity)??p(t.current_humidity),absHumidityGm3:p(t.abs_humidity_gm3),co2:p(t.co2)??p(t.carbon_dioxide),pmv:p(t.pmv),ppd:p(t.ppd),pmvValid:typeof t.pmv_valid=="boolean"?t.pmv_valid:null,ca:{deviationK:p(t.ca_deviation_k),timeInBand:p(t.ca_time_in_band),cyclesPerH:p(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,abs_humidity_floors:this._config.abs_humidity_floors,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:p(t.outdoor_co2)}),s=this._r,l=i.filter(a=>a.key==="pmv"?s.pmv:s.chips.has(a.key));return l.length?m`<div
      class="monitor"
      role="group"
      aria-label=${c(o,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,o))}
    </div>`:d}_lamp(t,r){let o=c(r,t.key),i=t.level==="unknown"?"unknown":`${t.key==="pmv"||t.key==="ca"?t.key:"air"}_${t.level}`,s=c(r,i),l="\u2014";t.value!=null&&(l=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let a=t.detailKey?c(r,t.detailKey):t.detail,u=`${o}: ${l} ${t.unit} \u2014 ${s}${a?` \xB7 ${a}`:""}`;return m`<div class="lamp" title=${u} aria-label=${u}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${o}</span>
      <span class="lv">${l}<small>${t.unit}</small></span>
    </div>`}_measurePill(t,r){let o=nt({active:t.active_comfort===!0,fanFirstPhase:typeof t.fan_first_phase=="string"?t.fan_first_phase:null,tier2FanCe:typeof t.tier2_fan_ce=="string"?t.tier2_fan_ce:null,tier2Pmv:typeof t.tier2_pmv_offset=="string"?t.tier2_pmv_offset:null,ceCreditK:p(t.fan_ce_credit_k),pmvOffsetK:p(t.pmv_offset_k),fanCeDwellMin:p(t.tier2_fan_ce_dwell_min),pmvDwellMin:p(t.tier2_pmv_dwell_min),dwellTargetMin:p(t.tier2_dwell_target_min),dwelling:typeof t.tier2_dwelling=="string"?t.tier2_dwelling:null});if(!o)return d;let i=[];o.fan&&i.push(c(r,"ac_fan")),o.ceK!=null&&i.push(`${c(r,"ac_ce")} +${o.ceK.toFixed(1)} K`),o.offsetK!=null&&i.push(`PMV ${o.offsetK>0?"+":""}${o.offsetK.toFixed(1)} K`);let s;return i.length?s=i.join(" \xB7 "):o.maturing?(s=c(r,o.dwellPaused?"ac_maturing_paused":"ac_maturing"),o.dwellMin!=null&&o.dwellTargetMin!=null&&(s+=` \xB7 ${Math.round(o.dwellMin/60)}/${Math.round(o.dwellTargetMin/60)} h`)):s=c(r,"ac_none"),m`<div class="learn">
      <div class="pill">${c(r,"ac_active")} · ${s}</div>
    </div>`}_learn(t,r){let o=p(t.confidence),i=this._r.learning&&o!=null,s=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!i&&!s)return d;let l=p(t.pi_setpoint),a=p(t.mpc_setpoint),u=t.tpi_active?`TPI ${Math.round(p(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return m`<div class="learn">
      ${i?m`<div class="bar">
            <i style="width:${((o??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${c(r,"learning")} ${((o??0)*100).toFixed(0)}%</span>`:d}
      ${s?m`<div class="pill">
            ${c(r,"shadow")}${u?m` · ${u}`:d}
          </div>`:d}
    </div>`}};X.properties={hass:{},_config:{state:!0}},X.styles=U`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .chip-alert { border: 1px solid var(--error-color, #e53935);
      color: var(--error-color, #e53935); }
    .chip-alert ha-icon { color: var(--error-color, #e53935); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .monitor { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 2px; }
    .lamp { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .lamp .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
    .lamp .lk { color: var(--secondary-text-color); }
    .lamp .lv { font-weight: 600; }
    .lamp .lv small { font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial:focus, .ctrclick:focus, .chips:focus { outline: none; }
    .dial:focus-visible, .ctrclick:focus-visible, .chips:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: 2px; border-radius: 10px;
    }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .opair { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    .mould { stroke: var(--warning-color, #ff9800); stroke-width: 3; stroke-linecap: round; }
    .mlbl { fill: var(--warning-color, #ff9800); font-size: 11px; font-weight: 600;
      text-anchor: middle; dominant-baseline: middle; }
    .dial.ro { cursor: default; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
    .preset { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
      border: 1px solid var(--divider-color, #e0e0e0); border-radius: 16px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color); font: inherit; font-size: 13px; cursor: pointer; }
    .preset ha-icon { --mdc-icon-size: 16px; }
    .preset.on { background: var(--primary-color, #2196f3);
      color: var(--text-primary-color, #fff); border-color: var(--primary-color, #2196f3); }
    .preset:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .preset em { font-style: normal; color: var(--secondary-text-color); margin-left: 2px; }
    .preset.on em { color: inherit; opacity: 0.85; }
    .hold { display: flex; align-items: center; gap: 6px; margin: 8px 0 2px; }
    .hold-chip { flex: 1 1 auto; }
    .resume { flex: none; display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; padding: 0; border: none; border-radius: 50%;
      background: var(--secondary-background-color); color: var(--secondary-text-color); cursor: pointer; }
    .resume ha-icon { --mdc-icon-size: 18px; }
    .resume:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .valid { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
    .wrap.compact { padding: 6px 12px 12px; }
    .wrap.compact .dialctr .op { font-size: 30px; }
    .wrap.compact .presets, .wrap.compact .monitor, .wrap.compact .chips { gap: 4px; }
    `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",X);console.info(`%c POISE-CARD ${ie} `,"background:#2196f3;color:#fff");export{X as PoiseCard};
