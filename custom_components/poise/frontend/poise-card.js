/* poise-card 0.167.0 — bundled, served by the Poise integration (ADR-0040) */
var J=globalThis,Q=J.ShadowRoot&&(J.ShadyCSS===void 0||J.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,me=Symbol(),Me=new WeakMap,U=class{constructor(e,t,o){if(this._$cssResult$=!0,o!==me)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(Q&&e===void 0){let o=t!==void 0&&t.length===1;o&&(e=Me.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),o&&Me.set(t,e))}return e}toString(){return this.cssText}},Le=n=>new U(typeof n=="string"?n:n+"",void 0,me),F=(n,...e)=>{let t=n.length===1?n[0]:e.reduce((o,r,s)=>o+(i=>{if(i._$cssResult$===!0)return i.cssText;if(typeof i=="number")return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+n[s+1],n[0]);return new U(t,n,me)},Re=(n,e)=>{if(Q)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let o=document.createElement("style"),r=J.litNonce;r!==void 0&&o.setAttribute("nonce",r),o.textContent=t.cssText,n.appendChild(o)}},fe=Q?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(let o of e.cssRules)t+=o.cssText;return Le(t)})(n):n;var{is:_t,defineProperty:gt,getOwnPropertyDescriptor:bt,getOwnPropertyNames:yt,getOwnPropertySymbols:vt,getPrototypeOf:xt}=Object,ee=globalThis,He=ee.trustedTypes,$t=He?He.emptyScript:"",wt=ee.reactiveElementPolyfillSupport,V=(n,e)=>n,_e={toAttribute(n,e){switch(e){case Boolean:n=n?$t:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},Oe=(n,e)=>!_t(n,e),Te={attribute:!0,type:String,converter:_e,reflect:!1,useDefault:!1,hasChanged:Oe};Symbol.metadata??=Symbol("metadata"),ee.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Te){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let o=Symbol(),r=this.getPropertyDescriptor(e,o,t);r!==void 0&&gt(this.prototype,e,r)}}static getPropertyDescriptor(e,t,o){let{get:r,set:s}=bt(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:r,set(i){let l=r?.call(this);s?.call(this,i),this.requestUpdate(e,l,o)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Te}static _$Ei(){if(this.hasOwnProperty(V("elementProperties")))return;let e=xt(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(V("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(V("properties"))){let t=this.properties,o=[...yt(t),...vt(t)];for(let r of o)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[o,r]of t)this.elementProperties.set(o,r)}this._$Eh=new Map;for(let[t,o]of this.elementProperties){let r=this._$Eu(t,o);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let o=new Set(e.flat(1/0).reverse());for(let r of o)t.unshift(fe(r))}else e!==void 0&&t.push(fe(e));return t}static _$Eu(e,t){let o=t.attribute;return o===!1?void 0:typeof o=="string"?o:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let o of t.keys())this.hasOwnProperty(o)&&(e.set(o,this[o]),delete this[o]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Re(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,o){this._$AK(e,o)}_$ET(e,t){let o=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,o);if(r!==void 0&&o.reflect===!0){let s=(o.converter?.toAttribute!==void 0?o.converter:_e).toAttribute(t,o.type);this._$Em=e,s==null?this.removeAttribute(r):this.setAttribute(r,s),this._$Em=null}}_$AK(e,t){let o=this.constructor,r=o._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let s=o.getPropertyOptions(r),i=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:_e;this._$Em=r;let l=i.fromAttribute(t,s.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,o,r=!1,s){if(e!==void 0){let i=this.constructor;if(r===!1&&(s=this[e]),o??=i.getPropertyOptions(e),!((o.hasChanged??Oe)(s,t)||o.useDefault&&o.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,o))))return;this.C(e,t,o)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:o,reflect:r,wrapped:s},i){o&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),s!==!0||i!==void 0)||(this._$AL.has(e)||(this.hasUpdated||o||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,s]of this._$Ep)this[r]=s;this._$Ep=void 0}let o=this.constructor.elementProperties;if(o.size>0)for(let[r,s]of o){let{wrapped:i}=s,l=this[r];i!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,s,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(o=>o.hostUpdate?.()),this.update(t)):this._$EM()}catch(o){throw e=!1,this._$EM(),o}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[V("elementProperties")]=new Map,w[V("finalized")]=new Map,wt?.({ReactiveElement:w}),(ee.reactiveElementVersions??=[]).push("2.1.2");var we=globalThis,De=n=>n,te=we.trustedTypes,Ie=te?te.createPolicy("lit-html",{createHTML:n=>n}):void 0,Be="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Ke="?"+C,Ct=`<${Ke}>`,P=document,B=()=>P.createComment(""),K=n=>n===null||typeof n!="object"&&typeof n!="function",Ce=Array.isArray,At=n=>Ce(n)||typeof n?.[Symbol.iterator]=="function",ge=`[ 	
\f\r]`,z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ne=/-->/g,Ue=/>/g,k=RegExp(`>|${ge}(?:([^\\s"'>=/]+)(${ge}*=${ge}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Fe=/'/g,Ve=/"/g,je=/^(?:script|style|textarea|title)$/i,Ae=n=>(e,...t)=>({_$litType$:n,strings:e,values:t}),m=Ae(1),qe=Ae(2),dn=Ae(3),M=Symbol.for("lit-noChange"),u=Symbol.for("lit-nothing"),ze=new WeakMap,E=P.createTreeWalker(P,129);function We(n,e){if(!Ce(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ie!==void 0?Ie.createHTML(e):e}var St=(n,e)=>{let t=n.length-1,o=[],r,s=e===2?"<svg>":e===3?"<math>":"",i=z;for(let l=0;l<t;l++){let a=n[l],d,f,h=-1,g=0;for(;g<a.length&&(i.lastIndex=g,f=i.exec(a),f!==null);)g=i.lastIndex,i===z?f[1]==="!--"?i=Ne:f[1]!==void 0?i=Ue:f[2]!==void 0?(je.test(f[2])&&(r=RegExp("</"+f[2],"g")),i=k):f[3]!==void 0&&(i=k):i===k?f[0]===">"?(i=r??z,h=-1):f[1]===void 0?h=-2:(h=i.lastIndex-f[2].length,d=f[1],i=f[3]===void 0?k:f[3]==='"'?Ve:Fe):i===Ve||i===Fe?i=k:i===Ne||i===Ue?i=z:(i=k,r=void 0);let x=i===k&&n[l+1].startsWith("/>")?" ":"";s+=i===z?a+Ct:h>=0?(o.push(d),a.slice(0,h)+Be+a.slice(h)+C+x):a+C+(h===-2?l:x)}return[We(n,s+(n[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),o]},j=class n{constructor({strings:e,_$litType$:t},o){let r;this.parts=[];let s=0,i=0,l=e.length-1,a=this.parts,[d,f]=St(e,t);if(this.el=n.createElement(d,o),E.currentNode=this.el.content,t===2||t===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(r=E.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let h of r.getAttributeNames())if(h.endsWith(Be)){let g=f[i++],x=r.getAttribute(h).split(C),$=/([.?@])?(.*)/.exec(g);a.push({type:1,index:s,name:$[2],strings:x,ctor:$[1]==="."?ye:$[1]==="?"?ve:$[1]==="@"?xe:H}),r.removeAttribute(h)}else h.startsWith(C)&&(a.push({type:6,index:s}),r.removeAttribute(h));if(je.test(r.tagName)){let h=r.textContent.split(C),g=h.length-1;if(g>0){r.textContent=te?te.emptyScript:"";for(let x=0;x<g;x++)r.append(h[x],B()),E.nextNode(),a.push({type:2,index:++s});r.append(h[g],B())}}}else if(r.nodeType===8)if(r.data===Ke)a.push({type:2,index:s});else{let h=-1;for(;(h=r.data.indexOf(C,h+1))!==-1;)a.push({type:7,index:s}),h+=C.length-1}s++}}static createElement(e,t){let o=P.createElement("template");return o.innerHTML=e,o}};function R(n,e,t=n,o){if(e===M)return e;let r=o!==void 0?t._$Co?.[o]:t._$Cl,s=K(e)?void 0:e._$litDirective$;return r?.constructor!==s&&(r?._$AO?.(!1),s===void 0?r=void 0:(r=new s(n),r._$AT(n,t,o)),o!==void 0?(t._$Co??=[])[o]=r:t._$Cl=r),r!==void 0&&(e=R(n,r._$AS(n,e.values),r,o)),e}var be=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:o}=this._$AD,r=(e?.creationScope??P).importNode(t,!0);E.currentNode=r;let s=E.nextNode(),i=0,l=0,a=o[0];for(;a!==void 0;){if(i===a.index){let d;a.type===2?d=new q(s,s.nextSibling,this,e):a.type===1?d=new a.ctor(s,a.name,a.strings,this,e):a.type===6&&(d=new $e(s,this,e)),this._$AV.push(d),a=o[++l]}i!==a?.index&&(s=E.nextNode(),i++)}return E.currentNode=P,r}p(e){let t=0;for(let o of this._$AV)o!==void 0&&(o.strings!==void 0?(o._$AI(e,o,t),t+=o.strings.length-2):o._$AI(e[t])),t++}},q=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,o,r){this.type=2,this._$AH=u,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=o,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=R(this,e,t),K(e)?e===u||e==null||e===""?(this._$AH!==u&&this._$AR(),this._$AH=u):e!==this._$AH&&e!==M&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):At(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==u&&K(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:o}=e,r=typeof o=="number"?this._$AC(e):(o.el===void 0&&(o.el=j.createElement(We(o.h,o.h[0]),this.options)),o);if(this._$AH?._$AD===r)this._$AH.p(t);else{let s=new be(r,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=ze.get(e.strings);return t===void 0&&ze.set(e.strings,t=new j(e)),t}k(e){Ce(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,o,r=0;for(let s of e)r===t.length?t.push(o=new n(this.O(B()),this.O(B()),this,this.options)):o=t[r],o._$AI(s),r++;r<t.length&&(this._$AR(o&&o._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let o=De(e).nextSibling;De(e).remove(),e=o}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},H=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,o,r,s){this.type=1,this._$AH=u,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=s,o.length>2||o[0]!==""||o[1]!==""?(this._$AH=Array(o.length-1).fill(new String),this.strings=o):this._$AH=u}_$AI(e,t=this,o,r){let s=this.strings,i=!1;if(s===void 0)e=R(this,e,t,0),i=!K(e)||e!==this._$AH&&e!==M,i&&(this._$AH=e);else{let l=e,a,d;for(e=s[0],a=0;a<s.length-1;a++)d=R(this,l[o+a],t,a),d===M&&(d=this._$AH[a]),i||=!K(d)||d!==this._$AH[a],d===u?e=u:e!==u&&(e+=(d??"")+s[a+1]),this._$AH[a]=d}i&&!r&&this.j(e)}j(e){e===u?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},ye=class extends H{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===u?void 0:e}},ve=class extends H{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==u)}},xe=class extends H{constructor(e,t,o,r,s){super(e,t,o,r,s),this.type=5}_$AI(e,t=this){if((e=R(this,e,t,0)??u)===M)return;let o=this._$AH,r=e===u&&o!==u||e.capture!==o.capture||e.once!==o.once||e.passive!==o.passive,s=e!==u&&(o===u||r);r&&this.element.removeEventListener(this.name,this,o),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},$e=class{constructor(e,t,o){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=o}get _$AU(){return this._$AM._$AU}_$AI(e){R(this,e)}};var kt=we.litHtmlPolyfillSupport;kt?.(j,q),(we.litHtmlVersions??=[]).push("3.3.3");var Ge=(n,e,t)=>{let o=t?.renderBefore??e,r=o._$litPart$;if(r===void 0){let s=t?.renderBefore??null;o._$litPart$=r=new q(e.insertBefore(B(),s),s,void 0,t??{})}return r._$AI(n),r};var Se=globalThis,v=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=Ge(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};v._$litElement$=!0,v.finalized=!0,Se.litElementHydrateSupport?.({LitElement:v});var Et=Se.litElementPolyfillSupport;Et?.({LitElement:v});(Se.litElementVersions??=[]).push("4.2.2");function Pt(n,e,t){return Math.min(Math.max(n,e),t)}function ne(n,e,t){return t<=e?.5:Pt((n-e)/(t-e),0,1)}function Mt(n,e,t){if(n==null)return"unknown";if(n<e)return"below";if(n>t)return"above";let o=t-e;if(o<=0)return"in_band";let r=(n-e)/o;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function Xe(n){let{operative:e,setpoint:t,low:o,high:r}=n;if(o==null||r==null||r<=o)return null;let s=o-1.5,i=r+1.5;return{low:o,high:r,span:r-o,operative:e,setpoint:t,category:n.category??"",verdict:Mt(e,o,r),axisLow:s,axisHigh:i,lowFrac:ne(o,s,i),highFrac:ne(r,s,i),operativeFrac:e==null?null:ne(e,s,i),setpointFrac:t==null?null:ne(t,s,i)}}var Ye={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function W(n){return Ye[n]??Ye.unknown}var Lt=[1e3,2e3],Rt=[30,40,60,65],Ht=[26,30],Tt=420,Ot=[800,1350];function _(n){return typeof n=="number"&&Number.isFinite(n)}function oe(n,e){return n&&n.length>=2&&_(n[0])&&_(n[1])&&n[0]<n[1]?[n[0],n[1]]:[e[0],e[1]]}function Dt(n,e){if(n&&n.length>=4&&n.slice(0,4).every(_)){let[t,o,r,s]=n;if(t<=o&&o<=r&&r<=s)return[t,o,r,s]}return[e[0],e[1],e[2],e[3]]}function It(n){if(n?.scheme==="en16798"){let e=_(n.outdoor)?n.outdoor:Tt,t=oe(n.enRise,Ot);return[e+t[0],e+t[1]]}return oe(n?.thresholds,Lt)}function Nt(n,e){if(!_(n))return"unknown";let[t,o]=It(e);return n>=o?"alert":n>=t?"warn":"ok"}function Ut(n,e){if(!_(n))return"unknown";let[t,o,r,s]=Dt(e,Rt);return n<t||n>=s?"alert":n<o||n>r?"warn":"ok"}function Ft(n){switch(n){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Vt(n,e){if(!_(n))return"unknown";let[t,o]=oe(e,Ht);return n>o?"alert":n>t?"warn":"ok"}var zt=[10,15];function Bt(n){return 100-95*Math.exp(-(.03353*n**4+.2179*n**2))}function Kt(n,e,t){let[o,r]=oe(t,zt),s=_(e)?e:_(n)?Bt(n):null;return s==null?"unknown":s>=r?"alert":s>=o?"warn":"ok"}var jt=[.5,1],qt=[3,6],Wt=[85,60];function Je(n){return n<=1?n*100:n}var Ze={unknown:-1,ok:0,warn:1,alert:2};function Gt(n){let e=[];if(_(n.deviationK)){let[t,o]=jt;e.push(n.deviationK>=o?"alert":n.deviationK>=t?"warn":"ok")}if(_(n.cyclesPerH)){let[t,o]=qt;e.push(n.cyclesPerH>=o?"alert":n.cyclesPerH>=t?"warn":"ok")}if(_(n.timeInBand)){let t=Je(n.timeInBand),[o,r]=Wt;e.push(t<r?"alert":t<o?"warn":"ok")}return e.length?e.reduce((t,o)=>Ze[o]>Ze[t]?o:t,"ok"):"unknown"}function Qe(n,e){let t=[],o=e?.temperature_scale==="asr_office"?Vt(n.temperature,e.asr_thresholds):Ft(n.comfortVerdict??null);if(t.push({key:"temperature",value:n.temperature,unit:"\xB0C",level:o,color:W(o)}),_(n.humidity)){let s=Ut(n.humidity,e?.humidity_thresholds);t.push({key:"humidity",value:n.humidity,unit:"%",level:s,color:W(s)})}if(_(n.co2)){let s=Nt(n.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:n.co2,unit:"ppm",level:s,color:W(s)})}if(_(n.pmv)||_(n.ppd)){let s=Kt(n.pmv??null,n.ppd??null);t.push({key:"pmv",value:_(n.ppd)?n.ppd:null,unit:"%",level:s,color:W(s)})}let r=n.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let s=Gt(r);t.push({key:"ca",value:_(r.timeInBand)?Je(r.timeInBand):null,unit:"%",level:s,color:W(s)})}return t}var ke=["hvac","window","temperature","humidity","co2","ca"],Xt=[12,24,48];function et(n,e,t){return typeof n=="string"&&e.includes(n)?n:t}function T(n,e){return typeof n=="boolean"?n:e}function Yt(n){return n===!1?new Set:n==null||n===!0?new Set(ke):Array.isArray(n)?new Set(n.filter(e=>ke.includes(e))):new Set(ke)}function Zt(n){if(n===!1)return{show:!1,hours:24};if(n===!0||n==null)return{show:!0,hours:24};let e=typeof n.hours=="number"?n.hours:Number(n.hours),t=Xt.includes(e)?e:24;return{show:T(n.show,!0),hours:t}}function tt(n){let e=n.sections??{},t=n.density?et(n.density,["comfortable","compact"],"comfortable"):n.compact?"compact":"comfortable";return{entity:n.entity,density:t,controls:et(n.controls,["dial","buttons","none"],"dial"),history:Zt(n.history),chips:Yt(e.chips),shadowPill:T(e.shadow_pill,T(n.show_shadow,!0)),learning:T(e.learning,!0),pmv:T(e.pmv,!0),presets:T(e.presets,!0),temperature_scale:n.temperature_scale,humidity_thresholds:n.humidity_thresholds,co2_scheme:n.co2_scheme,co2_thresholds:n.co2_thresholds}}var nt={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",manual:"Manual",resume_schedule:"Resume schedule",valid_until:"valid until",instead_of:"instead of",norm_limit:"norm limit",permanent:"permanent",compressor_guard:"Compressor guard",mould:"Mould limit",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},Jt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",manual:"Manuell",resume_schedule:"Zeitplan fortsetzen",valid_until:"gilt bis",instead_of:"statt",norm_limit:"Normgrenze",permanent:"dauerhaft",compressor_guard:"Verdichterschutz",mould:"Schimmelgrenze",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function c(n,e){return((n??"en").toLowerCase().startsWith("de")?Jt:nt)[e]??nt[e]??e}var Qt=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],en=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:Qt}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],tn={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},re=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${en}
      .computeLabel=${e=>tn[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};re.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",re);var se="0.167.0",ot=!1;function nn(){let n=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(n,n):n()}async function ie(n,e){if(!(ot||!e?.connection)){ot=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==se){let o=e.locale?.language;n.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${c(o,"update_msg")} (${se} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:c(o,"reload"),action:nn}},bubbles:!0,composed:!0}))}}catch{}}}function G(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var X=class extends v{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(o=>o.startsWith("binary_sensor.")&&e.states[o].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&ie(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,o=t?this.hass.states[t]:void 0;if(!o)return m`<ha-card
        ><div class="empty">${c(e,"no_system")}</div></ha-card
      >`;let r=o.attributes,s=o.state==="on",i=G(r.flow_target),l=G(r.shed_count)??0,a=r.source_grants??{},d=Object.keys(a);return m`<ha-card .header=${c(e,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${c(e,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${s?"on":""}">
          <ha-icon icon=${s?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${s?c(e,"demand_on"):c(e,"demand_off")}</span>
          ${r.frost_override?m`<em class="frost">${c(e,"frost")}</em>`:u}
        </div>
        <div class="stats">
          <div>
            <strong>${G(r.active_zones)??0}</strong
            ><span>${c(e,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${G(r.controlling_zones)??0}/${G(r.zone_count)??0}</strong
            ><span>${c(e,"zones")}</span>
          </div>
          ${i!=null?m`<div>
                <strong>${i.toFixed(0)}°</strong><span>${c(e,"flow")}</span>
              </div>`:u}
          ${l>0?m`<div>
                <strong>${l}</strong><span>${c(e,"shed")}</span>
              </div>`:u}
        </div>
        ${d.length?m`<div class="grants">
              ${d.map(f=>m`<span class="chip">${f}: ${a[f]}</span>`)}
            </div>`:u}
      </div>
    </ha-card>`}};X.properties={hass:{},_config:{state:!0}},X.styles=F`
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
  `;var ae=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${e=>e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};ae.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",ae);customElements.get("poise-system-card")||customElements.define("poise-system-card",X);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function rt(n,e,t){return Math.min(Math.max(n,e),t)}function st(n,e,t,o=300,r=90,s=1){let i=[];for(let b of n)b.op!=null&&i.push(b.op),b.sp!=null&&i.push(b.sp);if(e!=null&&i.push(e),t!=null&&i.push(t),i.length===0||n.length===0)return null;let l=Math.min(...i)-s,a=Math.max(...i)+s,d=n[0].t,h=n[n.length-1].t-d||1,g=a-l||1,x=b=>(b-d)/h*o,$=b=>r-(b-l)/g*r,I=b=>n.filter(S=>b(S)!=null).map(S=>`${x(S.t).toFixed(1)},${$(b(S)).toFixed(1)}`).join(" ");return{width:o,height:r,opPath:I(b=>b.op),spPath:I(b=>b.sp),bandTop:t==null?0:rt($(t),0,r),bandBottom:e==null?r:rt($(e),0,r),vMin:l,vMax:a}}var y={min:16,max:28,start:135,sweep:270};function it(n,e,t){return Math.min(Math.max(n,e),t)}function O(n,e=y){let t=it((n-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function on(n,e=y){let t=n;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let o=t-(e.start+e.sweep);return e.start+360-t<o?e.start:e.start+e.sweep}function rn(n,e=y){let o=(on(n,e)-e.start)/e.sweep;return e.min+o*(e.max-e.min)}function A(n,e,t,o){let r=o*Math.PI/180;return{x:n+t*Math.cos(r),y:e+t*Math.sin(r)}}function Ee(n,e,t,o,r){if(r<=o)return"";let s=A(n,e,t,o),i=A(n,e,t,r),l=r-o>180?1:0;return`M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${i.x.toFixed(2)} ${i.y.toFixed(2)}`}function at(n,e,t=y){let o=Math.atan2(e,n)*180/Math.PI;return o<0&&(o+=360),rn(o,t)}function lt(n,e,t,o=y){let r;switch(n){case"ArrowUp":case"ArrowRight":r=e+t;break;case"ArrowDown":case"ArrowLeft":r=e-t;break;case"PageUp":r=e+t*5;break;case"PageDown":r=e-t*5;break;case"Home":r=o.min;break;case"End":r=o.max;break;default:return null}return Math.round(it(r,o.min,o.max)/t)*t}function Pe(n,e=Date.now()){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:Math.max(0,Math.round((t-e)/6e4))}function ct(n,e){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:new Date(t).toLocaleTimeString(e,{hour:"2-digit",minute:"2-digit"})}function D(n){let e=n.temperature,t=typeof e=="string"?parseFloat(e):e;return typeof t=="number"&&!Number.isNaN(t)?t:null}function dt(n,e,t,o,r=Date.now()){let s=c(n,"manual");return t==="permanent"?{label:`${s} (${c(n,"permanent")})`,minutes:null,permanent:!0}:{label:e!=null?`${s} ${e.toFixed(1)}\xB0`:s,minutes:Pe(o,r),permanent:!1}}function ut(n,e,t){return e==null||t==null?c(n,"override_clamped"):`${e.toFixed(1)}\xB0 ${c(n,"instead_of")} ${t.toFixed(1)}\xB0 (${c(n,"norm_limit")})`}function pt(n,e,t){let o=e==null?"none":String(e).toLowerCase();return o==="none"||t?null:{key:o,label:c(n,o)||o}}function ht(n,e){n.callService("poise","resume_schedule",{entity_id:e})}function mt(n){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[n]??"mdi:tune"}function p(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var Y=class extends v{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=y}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(r=>r.startsWith("climate.")&&t.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=tt(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let o=t.get("hass");return!o||!this._config?.entity?!0:o.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let o=this._config.entity;if(!o||!this.hass)return;let r=this.hass.states[o];if(!r)return;let s=p(r.attributes.target_temperature_step)??.5,i=this._pending??D(r.attributes)??21;this.hass.callService("climate","set_temperature",{entity_id:o,temperature:Math.round((i+t*s)*10)/10})}updated(){this.hass&&ie(this,this.hass);let t=this._config?.entity;t&&this.hass&&this._r?.history.show&&this._histFor!==t&&(this._histFor=t,this._loadHistory(t))}async _loadHistory(t){if(!this.hass.connection)return;let o=this._r?.history.hours??24,r=new Date,s=new Date(r.getTime()-o*3600*1e3);try{let l=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:s.toISOString(),end_time:r.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],a={},d=[];for(let f of l){f.a&&(a={...a,...f.a});let h=(p(f.lu)??p(f.lc)??0)*1e3;d.push({t:h,op:p(a.operative_temperature)??p(a.current_temperature),sp:p(a.temperature)})}this._history=d,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,o){let r=st(this._history,t,o,300,80);return r?m`<svg
      class="chart"
      viewBox="0 0 ${r.width} ${r.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${r.bandTop}
        width=${r.width}
        height=${Math.max(0,r.bandBottom-r.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${r.spPath} class="csp"></polyline>
      <polyline points=${r.opPath} class="cop"></polyline>
    </svg>`:u}render(){let t=this.hass?.locale?.language,o=this._config?.entity,r=o?this.hass.states[o]:void 0;if(!r)return m`<ha-card
        ><div class="empty">${c(t,"no_entity")}</div></ha-card
      >`;let s=r.attributes,i=p(s.operative_temperature)??p(s.current_temperature),l=p(s.heat_sp)??p(s.temperature),a=Xe({operative:i,setpoint:l,low:p(s.comfort_low),high:p(s.comfort_high),category:s.category??null}),d=this._r;return m`<ha-card .header=${s.friendly_name??"Poise"}>
      <div class="wrap ${d.density==="compact"?"compact":""}">
        ${this._dial(s,t)}
        <div class="verdict">
          ${a?c(t,a.verdict):c(t,"unknown")}
          ${a?.category?m`<span class="cat">Kat. ${a.category}</span>`:u}
        </div>
        ${this._holdPill(s,t)}
        ${d.controls==="buttons"?this._control(this._pending??l,t):u}
        ${this._presets(s,t)}
        ${d.history.show?this._chart(p(s.comfort_low),p(s.comfort_high)):u}
        ${this._monitor(s,a,t)} ${this._chips(s,t)}
        ${this._learn(s,t)}
      </div>
    </ha-card>`}_dial(t,o){let r=p(t.operative_temperature)??p(t.current_temperature),s=D(t),i={min:p(t.min_temp)??y.min,max:p(t.max_temp)??y.max,start:y.start,sweep:y.sweep};this._dialCfg=i.max>i.min?i:y;let l=this._pending??s??r??this._dialCfg.min,a=p(t.comfort_low),d=p(t.comfort_high),f=100,h=100,g=80,x=Ee(f,h,g,y.start,y.start+y.sweep),$=a!=null&&d!=null?Ee(f,h,g,O(Math.min(a,d),this._dialCfg),O(Math.max(a,d),this._dialCfg)):"",I=String(t.hvac_action??""),b=I==="heating"?"heat":I==="cooling"?"cool":"",S=A(f,h,g,O(l,this._dialCfg)),le=r!=null?A(f,h,g,O(r,this._dialCfg)):null,L=p(t.mould_floor),N=L!=null&&L>this._dialCfg.min&&L<this._dialCfg.max,ce=N?O(L,this._dialCfg):0,de=N?A(f,h,g-9,ce):null,ue=N?A(f,h,g+9,ce):null,pe=N?A(f,h,g+17,ce):null,he=this._r.controls==="dial",Z=this._dragging?ct(t.override_expires_at,o):null,ft=`${l.toFixed(1)} \xB0C${Z?` \xB7 ${c(o,"valid_until")} ${Z}`:""}`;return m`<div class="dialwrap">
      <svg
        class="dial ${he?"":"ro"}"
        viewBox="0 0 200 200"
        role=${he?"slider":"img"}
        tabindex=${he?0:-1}
        aria-label=${c(o,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${l}
        aria-valuetext=${ft}
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${x}></path>
        <path class="bandarc" d=${$}></path>
        ${N&&de&&ue&&pe?qe`<line class="mould" x1=${de.x.toFixed(1)} y1=${de.y.toFixed(1)} x2=${ue.x.toFixed(1)} y2=${ue.y.toFixed(1)}><title>${c(o,"mould")} ${L.toFixed(1)}°</title></line><text class="mlbl" x=${pe.x.toFixed(1)} y=${pe.y.toFixed(1)}>${L.toFixed(0)}°</text>`:u}
        <circle
          class="opdot"
          cx=${(le?.x??0).toFixed(1)}
          cy=${(le?.y??0).toFixed(1)}
          r=${le?5:0}
        ></circle>
        <circle class="handle ${b}" cx=${S.x.toFixed(1)} cy=${S.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${c(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op">${r!=null?r.toFixed(1):"\u2014"}<span>°C</span></div>
          <div class="soll">${c(o,"setpoint")} <b>${l.toFixed(1)}°</b></div>
          ${Z?m`<div class="valid">${c(o,"valid_until")} ${Z}</div>`:u}
        </div>
      </div>
    </div>`}_fromPointer(t,o){let r=o.getBoundingClientRect();if(!r.width||!this._config.entity)return;let s=(t.clientX-r.left)/r.width*200-100,i=(t.clientY-r.top)/r.height*200-100,l=p(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(at(s,i,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let o=t.currentTarget;o.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,o)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let o=this._config.entity;if(!o||this._r.controls!=="dial")return;let r=this.hass.states[o];if(!r)return;let s=p(r.attributes.target_temperature_step)??.5,i=this._pending??D(r.attributes)??this._dialCfg.min,l=lt(t.key,i,s,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:o,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,o){return m`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${c(o,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let o=this._config.entity;!o||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:o,preset_mode:t})}_resumeSchedule(){let t=this._config.entity;!t||!this.hass||ht(this.hass,t)}_presets(t,o){if(!this._r.presets)return u;let r=t.preset_modes;if(!Array.isArray(r)||!r.length)return u;let s=t.preset_mode==null?null:String(t.preset_mode),i=Pe(t.boost_expires_at);return m`<div class="presets" role="group" aria-label=${c(o,"presets")}>
      ${r.map(l=>{let a=String(l),d=a.toLowerCase();return m`<button
          class="preset ${s===a?"on":""}"
          aria-pressed=${s===a?"true":"false"}
          @click=${()=>this._setPreset(a)}
        >
          <ha-icon icon=${mt(d)}></ha-icon>
          <span>${c(o,d)||a}</span>
          ${d==="boost"&&i!=null?m`<em>${i} ${c(o,"min_left")}</em>`:u}
        </button>`})}
    </div>`}_holdPill(t,o){if(!t.override_active)return u;let r=D(t),s=dt(o,r,t.override_policy,t.override_expires_at);return m`<div class="hold">
      <div class="chip hold-chip">
        <ha-icon icon="mdi:hand-back-right"></ha-icon><span>${s.label}</span>
        ${s.minutes!=null?m`<em>· ${s.minutes} ${c(o,"min_left")}</em>`:u}
      </div>
      <button
        class="resume"
        aria-label=${c(o,"resume_schedule")}
        title=${c(o,"resume_schedule")}
        @click=${this._resumeSchedule}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`}_chips(t,o){let r=this._r,s=[];if(r.chips.has("hvac")){t.preheating&&s.push(this._chip("mdi:fire-circle",c(o,"preheating"),t.minutes_to_comfort,o)),t.coasting&&s.push(this._chip("mdi:coffee",c(o,"coasting"),t.minutes_to_setback,o));let i=pt(o,t.preset,r.presets);i&&s.push(this._chip(mt(i.key),i.label)),t.heating_failure&&s.push(this._chip("mdi:alert",c(o,"failure"))),t.override_clamped&&s.push(this._chip("mdi:arrow-collapse-vertical",ut(o,D(t),p(t.override_requested)))),t.mode_nudge_blocked&&s.push(this._chip("mdi:timer-sand",`${c(o,"compressor_guard")}: ${t.mode_nudge_blocked}`));let l=t.binding_lower_cause;l&&l!=="en16798"&&s.push(this._chip("mdi:shield-alert",String(l)))}return r.chips.has("window")&&(t.window_open&&s.push(this._chip("mdi:window-open",c(o,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&s.push(this._chip("mdi:window-closed-variant",c(o,"bypass")))),s.length?m`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${c(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${s}
        </div>`:u}_chip(t,o,r,s){let i=p(r);return m`<div class="chip">
      <ha-icon icon=${t}></ha-icon><span>${o}</span>
      ${i!=null?m`<em>${Math.round(i)} ${c(s,"min_left")}</em>`:u}
    </div>`}_monitor(t,o,r){let s=Qe({temperature:p(t.operative_temperature)??p(t.current_temperature),comfortVerdict:o?.verdict??null,humidity:p(t.humidity)??p(t.current_humidity),co2:p(t.co2)??p(t.carbon_dioxide),pmv:p(t.pmv),ppd:p(t.ppd),ca:{deviationK:p(t.ca_deviation_k),timeInBand:p(t.ca_time_in_band),cyclesPerH:p(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:p(t.outdoor_co2)}),i=this._r,l=s.filter(a=>a.key==="pmv"?i.pmv:i.chips.has(a.key));return l.length?m`<div
      class="monitor"
      role="group"
      aria-label=${c(r,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,r))}
    </div>`:u}_lamp(t,o){let r=c(o,t.key),s=c(o,t.level==="unknown"?"unknown":"air_"+t.level),i="\u2014";t.value!=null&&(i=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let l=`${r}: ${i} ${t.unit} \u2014 ${s}`;return m`<div class="lamp" title=${l} aria-label=${l}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${i}<small>${t.unit}</small></span>
    </div>`}_learn(t,o){let r=p(t.confidence),s=this._r.learning&&r!=null,i=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!s&&!i)return u;let l=p(t.pi_setpoint),a=p(t.mpc_setpoint),d=t.tpi_active?`TPI ${Math.round(p(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return m`<div class="learn">
      ${s?m`<div class="bar">
            <i style="width:${((r??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${c(o,"learning")} ${((r??0)*100).toFixed(0)}%</span>`:u}
      ${i?m`<div class="pill">
            ${c(o,"shadow")}${d?m` · ${d}`:u}
          </div>`:u}
    </div>`}};Y.properties={hass:{},_config:{state:!0}},Y.styles=F`
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
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",Y);console.info(`%c POISE-CARD ${se} `,"background:#2196f3;color:#fff");export{Y as PoiseCard};
